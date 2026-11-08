"""The operator console's backend: protocol section 21.

Section 21.1 is the rule the rest rests on. **The console renders and does not compute.** Every
figure it serves is read from a run manifest; where it needs a figure no manifest carries, the
harness that owns that figure is extended to publish it and the results table gains a row for it.

That rule is not fastidiousness. A console that computes its own figures is a second implementation
of the domain, and this project has twice recorded what happens when a second implementation is
mistaken for a verification: section 14.3's integrity walk and section 20.2's recorded-time walk
both share code with the thing they check, and both had to retract the word independent. A display
that recomputed a shortfall would be a third, with no gate at all and the widest audience.
"""

from __future__ import annotations

from typing import Final

CONSOLE_VERSION: Final[str] = "console-v0"
