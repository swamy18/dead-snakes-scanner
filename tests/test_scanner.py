from __future__ import annotations
import subprocess
import tempfile
import textwrap
from pathlib import Path
import pytest
from dead_snakes_scanner import main, scan_path

TEST_CODE = '''
x = {"a":1}
print x
print(x)
for k in x.iterkeys():
    pass
for v in x.itervalues():
    pass
for kv in x.iteritems():
    pass
y = "hello %s" % "world"
import os
os.path.join("a","b")
xrange(5)
basestring
unicode("x")
try:
    pass
except Exception, e:
    pass
'''


def test_scanner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        py = repo / "test.py"
        py.write_text(textwrap.dedent(TEST_CODE))
        relics = list(scan_path(repo))
        assert len(relics) == 10
        kinds = {r[3] for r in relics}
        expected = {
            "print statement",
            "iterkeys",
            "itervalues",
            "iteritems",
            "% formatting",
            "os.path.join",
            "xrange",
            "basestring",
            "unicode",
            "except E, e:",
        }
        assert kinds == expected


def test_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        py = repo / "test.py"
        py.write_text("print 'hello'")
        proc = subprocess.run([sys.executable, "dead_snakes_scanner.py", str(repo)], capture_output=True, text=True)
        assert proc.returncode == 1
        assert "print statement" in proc.stdout


def test_json() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        py = repo / "test.py"
        py.write_text("print 'hello'")
        env = {**os.environ, "DEAD_SNAKES_JSON": "1"}
        proc = subprocess.run([sys.executable, "dead_snakes_scanner.py", str(repo)], capture_output=True, text=True, env=env)
        assert proc.returncode == 1
        data = json.loads(proc.stdout)
        assert data["relic"] == "print statement"
