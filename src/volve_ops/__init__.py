"""Evidence-bound operational investigation over the Volve open dataset."""

__all__ = ["INGEST_VERSION"]

# Bumped whenever ingest behaviour changes in a way that could alter what reaches the
# canonical store. Recorded in every run manifest as parser_version.
INGEST_VERSION = "ingest-v0"
