#!/usr/bin/env bash
# Run the CI jobs the way a runner runs them: from a clean clone, with no dataset.
#
#     bash scripts/check_like_ci.sh
#
# The dataset is gitignored, so a developer's checkout has it and no runner does. Every CI failure
# this project has had came from verifying a fix in an environment that has it: a missing optional
# extra that local mypy could resolve, and two tests that read a run manifest without declaring it.
# Both passed locally and failed on every push.
#
# This copies the **tracked files as they currently are**, uncommitted changes included, into a
# temporary directory and runs what `.github/workflows/ci.yml` runs. The working tree rather than
# HEAD on purpose: the question worth answering is what CI will say about the commit you are about
# to make, and checking HEAD answers it one commit too late. It is slow, a few minutes, and it is
# the only check that asks the question CI asks.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "copying the tracked working tree into a data-free checkout"
mkdir -p "$work/repo"
# `git ls-files` lists exactly what is tracked, so an untracked or ignored path cannot come along.
# That is the property this check rests on: the dataset, the venv and `_private/` stay behind.
(cd "$repo" && git ls-files -z | tar --null -T - -cf -) | (cd "$work/repo" && tar -xf -)
cd "$work/repo"
test ! -d data || { echo "the copy carries a data/ directory; this check cannot do its job" >&2; exit 1; }
test ! -d _private || { echo "the copy carries _private/; this check cannot do its job" >&2; exit 1; }

echo "=== job: checks"
python3 -m venv .venv-checks
.venv-checks/bin/pip install --quiet --upgrade pip
.venv-checks/bin/pip install --quiet -e ".[dev,mcp,console]"
# Against the source repository, because the copy is not a git checkout. Same expression the
# workflow uses, so a path that would fail there fails here.
git -C "$repo" ls-files | grep -iE '(^|/)_private/|(^|/)handoff|console_decisions|learning_notes|(^|/)data/|(^|/)\.env$' \
  && { echo "a tracked path must never be committed" >&2; exit 1; } || echo "  no private, data or secret paths tracked"
.venv-checks/bin/ruff check .
.venv-checks/bin/ruff format --check .
.venv-checks/bin/mypy
.venv-checks/bin/python -m pytest -q

# Section 22's marks. CI runs this unconditionally, and it is the step that crashed on a clean
# clone writing its own manifest into a directory that does not exist. The script that exists to
# ask "what will CI say" did not run it, so it could not have caught that.
.venv-checks/bin/python scripts/run_security_checks.py

echo "=== job: without-optional-extras"
python3 -m venv .venv-core
.venv-core/bin/pip install --quiet --upgrade pip
.venv-core/bin/pip install --quiet -e ".[dev]"
.venv-core/bin/python -c "import mcp" 2>/dev/null && { echo "mcp present" >&2; exit 1; } || echo "  mcp absent"
.venv-core/bin/python -c "import fastapi" 2>/dev/null && { echo "fastapi present" >&2; exit 1; } || echo "  fastapi absent"
.venv-core/bin/python -m pytest -q

echo "=== job: frontend"
npm ci --prefix frontend --silent
npm run lint --prefix frontend --silent
npm run build --prefix frontend --silent

echo
echo "all three jobs pass from a clean, data-free clone"
