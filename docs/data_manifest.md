# Data manifest

Version: v0, schema only
Date: 2026-10-04

Raw and processed Volve data are never committed to this repository. This manifest is
what gets committed instead: enough metadata for a reader to obtain the same files and
verify they have the same bytes.

As of this version no data has been retrieved, so every table below is empty by
design. The tables are filled when the dataset is first retrieved, after its licence has
been reviewed and accepted by the project owner. Licence and attribution terms are
recorded in files created at that point; they do not exist yet.

## Source

| Field | Value |
|---|---|
| Dataset | Equinor Volve open dataset |
| Source URL | to be recorded at retrieval |
| Access method | to be recorded at retrieval |
| Dataset version or release | to be recorded at retrieval |
| Dataset release date | to be recorded at retrieval |
| Licence | to be recorded after review |
| Licence version as published at retrieval | to be recorded at retrieval |
| Attribution required | to be recorded after review |
| Redistribution of derived extracts permitted | to be recorded after review |
| Retrieved by | project owner, personal account |
| Retrieval date | to be recorded |

## Files

One row per file used by the project. Files examined and rejected are listed in the
next table rather than deleted from the record, because knowing what was looked at and
discarded is part of knowing what the results rest on.

| File | Source path or URL | Kind | Size (bytes) | SHA-256 | Retrieved | Used by |
|---|---|---|---|---|---|---|

## Examined and not used

Files that were opened and then set aside. Kept in the record, because knowing what was
looked at and discarded is part of knowing what the results rest on.

| File | Kind | Reason not used |
|---|---|---|

## Not retrieved

Whole collections deliberately left alone, so that a reader can tell the difference
between data judged irrelevant and data never looked at. The dataset is far larger than
this project needs.

| Collection | Why not retrieved |
|---|---|

## Reproduction

The commands or steps that reproduce this exact file set, recorded at retrieval. A
fresh checkout plus these steps must produce files whose checksums match the table
above. If any part of acquisition cannot be scripted, for example a licence acceptance
or an interactive download, that step is written out as a manual instruction rather
than omitted.

To be completed at retrieval.

## Verification

```
# to be added alongside the file table: recompute and compare checksums
```
