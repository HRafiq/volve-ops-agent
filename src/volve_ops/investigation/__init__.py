"""The investigation layer: a bounded controller over the deterministic services.

Protocol section 18 is the specification. The controller owns the stages and the stop conditions;
the model's judgement is exercised inside them and never asked what to do next from an open list.
"""

from typing import Final

INVESTIGATOR_VERSION: Final[str] = "investigator-v0"
