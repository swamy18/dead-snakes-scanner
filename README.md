# dead-snakes-scanner
Ever wonder if your repos still reference Python releases that reached end-of-life? Drop this tiny scanner into your CI (or run it locally) and it will crawl Dockerfiles, requirements, setup.cfg, pyproject.toml, GitHub Actions, tox.ini, etc. and fail the build if any EOL “snake” is found. Keeps your projects safe, modern and green.
