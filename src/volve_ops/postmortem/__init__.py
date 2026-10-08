"""The post-mortem, the lessons register and the correction store, per protocol section 20.

No model is involved in any of it. The post-mortem is an aggregation of the source's own fields, the
register groups those fields, and the correction store records what a person changed.
"""

from typing import Final

POSTMORTEM_VERSION: Final[str] = "postmortem-v0"
