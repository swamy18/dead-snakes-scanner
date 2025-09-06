from __future__ import annotations
import ast
import json
import os
import re
import subprocess
import sys
import textwrap
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence, Tuple

try:
    from rich.console import Console
    from rich.table import Table

    HAS_RICH = True
except ImportError:  # pragma: no cover
    HAS_RICH = False

RELIC = Tuple[str, int, int, str, str]


def main(argv: Sequence[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1 or argv[0] in {"-h", "--help"}:
        print("usage: dead-snakes-scanner <repo-url-or-local-path>", file=sys.stderr)
        return 2
    target = argv[0]
    json_out = os.getenv("DEAD_SNAKES_JSON", "").lower() in {"1", "true"}
    pr_mode = os.getenv("DEAD_SNAKES_PR", "").lower() in {"1", "true"}

    path = Path(target) if not target.startswith(("http://", "https://")) else _clone(target)
    relics: List[RELIC] = list(scan_path(path))
    if relics:
        if json_out:
            for r in relics:
                print(json.dumps(dict(file=r[0], line=r[1], col=r[2], relic=r[3], snippet=r[4])))
        elif HAS_RICH and not pr_mode:
            table = Table(title="Dead Snakes")
            for h in ["file", "line", "col", "relic", "snippet"]:
                table.add_column(h)
            for r in relics:
                table.add_row(*map(str, r))
            Console().print(table)
        else:  # plain fallback
            for r in relics:
                print(f"{r[0]}:{r[1]}:{r[2]} {r[3]} {r[4]}")
        if pr_mode:
            _post_pr_comment(relics)
        return 1
    return 0


def _clone(url: str) -> Path:
    tmp = Path(os.getenv("RUNNER_TEMP", "/tmp")) / "dss"
    subprocess.run(["git", "clone", "--depth", "1", url, str(tmp)], check=True, capture_output=True)
    return tmp


def scan_path(root: Path) -> Iterator[RELIC]:
    for py in root.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except Exception:  # pragma: no cover
            continue
        yield from Visitor(str(py), tree).run()


class Visitor(ast.NodeVisitor):
    def __init__(self, filename: str, tree: ast.AST) -> None:
        self.filename = filename
        self.tree = tree
        self.out: List[RELIC] = []

    def run(self) -> List[RELIC]:
        self.visit(self.tree)
        return self.out

    def _add(self, node: ast.AST, relic: str, snippet: str | None = None) -> None:
        self.out.append(
            (
                self.filename,
                node.lineno,
                node.col_offset,
                relic,
                snippet or textwrap.get_source_segment(snippet or "", node) or "",
            )
        )

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mod):
            if not (isinstance(node.parent, ast.Call) and isinstance(node.parent.func, ast.Attribute) and node.parent.func.attr == "debug"):  # type: ignore
                self._add(node, "% formatting")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in {"iteritems", "iterkeys", "itervalues"}:
            self._add(node, node.attr)
        if node.attr == "join" and isinstance(node.value, ast.Attribute) and node.value.attr == "path":
            self._add(node, "os.path.join")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in {"xrange", "basestring", "unicode"}:
            self._add(node, node.id)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name and isinstance(node.name, str) and "," in str(ast.dump(node)):  # type: ignore
            self._add(node, "except E, e:")

    def visit_Print(self, node: ast.Print) -> None:  # type: ignore
        self._add(node, "print statement")


def _post_pr_comment(relics: List[RELIC]) -> None:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    pr = os.getenv("GITHUB_PR_NUMBER")
    if not (token and repo and pr):
        print("Missing env for PR comment", file=sys.stderr)
        return
    body = "## Dead Snakes Report\n"
    if HAS_RICH:
        table = Table()
        for h in ["file", "line", "col", "relic", "snippet"]:
            table.add_column(h)
        for r in relics:
            table.add_row(*map(str, r))
        console = Console(file=None, width=120)
        console.begin_capture()
        console.print(table)
        body += console.end_capture()
    else:
        for r in relics:
            body += f"{r[0]}:{r[1]}:{r[2]} {r[3]} {r[4]}\n"
    url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    # find existing comment
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        comments: List[Dict[str, Any]] = json.load(resp)
    existing = next((c for c in comments if c["user"]["login"] == "github-actions[bot]" and "Dead Snakes Report" in c["body"]), None)
    data = json.dumps({"body": body}).encode()
    if existing:
        url = existing["url"]
        req = urllib.request.Request(url, data=data, headers=headers, method="PATCH")
    else:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    urllib.request.urlopen(req)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
