"""Extraction of non-productive time from daily drilling reports.

Deterministic first, by design. The category and the duration come from the source's own
fields, and only the cause is left to a model, because only the cause needs reading.
"""

EXTRACTOR_VERSION = "extractor-v0"
