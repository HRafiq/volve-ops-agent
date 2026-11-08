"""The operator console's HTTP layer. Protocol section 21.

A package rather than a loose module so that `scripts/run_console_checks.py` can import the route
table for section 21.6 mark 7. Before this existed the harness caught `ModuleNotFoundError` and
reported "fastapi is not installed", which was false: FastAPI was installed and the repository root
simply was not on the path. A gate that examines nothing is bad; a gate that examines nothing and
blames the wrong thing is worse, because it sends the next reader somewhere there is no defect.
"""

from __future__ import annotations
