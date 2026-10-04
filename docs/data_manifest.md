# Data manifest

Version: v1
Date: 2026-10-04

Raw and processed data are never committed to this repository. This manifest is what gets
committed instead: enough metadata for a reader to obtain the same inputs and verify they have
the same bytes.

## Source

| Field | Value |
|---|---|
| Dataset | Equinor Volve open dataset, "Volve Data Village" |
| Access route | Databricks Marketplace share, installed into a catalog volume |
| Volume path at retrieval | `/Volumes/equinor_asa_volve_data_village/public/volve` |
| Share size as listed | ~5,000 GB, overwhelmingly seismic and reservoir models |
| Licence | Equinor Open Data Licence; terms document included in the share |
| Attribution | Equinor and the former Volve licence partners |
| Redistribution | The dataset may not be resold |
| Retrieved by | the project owner, personal account |
| Retrieval date | 2026-10-04 |
| Availability note | A share installation is removed after 90 days and must be reinstalled; the volume path can change, so checksums rather than paths tie a result to its inputs. |

## Files

Paths are relative to the volume root above.

| File | Source path | Kind | Size (bytes) | SHA-256 | Retrieved | Used by |
|---|---|---|---|---|---|---|
| Volve production data.xlsx | Production_data/ | xlsx | 2342595 | 514d4e38763e09be7fbad12313429909b9799b1a6ec999bf5f36e0df1b6c9cae | 2026-10-04 | production profiling, C1 |

## Collections

Sets of files read as a group. The tree hash is the SHA-256 of the sorted `name sha256` lines
for every file in the set, so a single value verifies the whole collection and names the file
that changed when it does not match.

| Collection | Source path | Files | Size (bytes) | Tree hash | Used by |
|---|---|---:|---:|---|---|
| Daily drilling reports, XML | Well_technical_data/Daily Drilling Report - XML Version/ | 1759 | 21315879 | 6247ca2b021740975fdeb2e35cea2da64d33f32884d75dcbe527b76633e62315 | DDR profiling, B1, NPT design |
| Drilling programmes, PDF | Well_logs/14.DIV. REPORTS/*/ | 18 | 162855643 | 017a01b1c3e93ef8d8408e45b9433471d828c2fd2be9cc0218777be254737bc5 | B1 |

## Examined and not used

| Collection | Why not used |
|---|---|
| WITSML realtime drilling data | Terse operational event stream, median 18 characters per message, and not a narrative record. Carries per-record identifying metadata, see ADR 0006. |
| Reports/ | Two field-level documents, a discovery report and a development plan. Not per-well operational evidence. |
| PI System Manager Sleipner | Process tags for a different field. Checked for C1 and not applicable. |

## Not retrieved

Deliberately left alone, so a reader can tell data judged irrelevant from data never looked at.

| Collection | Why not retrieved |
|---|---|
| Seismic | Several terabytes of survey data. Outside the scope of a production and drilling investigation system. |
| Reservoir models, Eclipse and RMS | Simulation models. The system reasons about measured history, not model output. |
| Geophysical interpretations, GeoScience archive | Subsurface interpretation products, not operational evidence. |
| Well logs | Petrophysical logs. Not used by the capabilities built here. |

## Reproduction

1. Obtain access to the Volve Data Village share through Equinor's published route and accept
   the dataset licence. This step is manual and cannot be scripted.
2. Install the share into a catalog volume. Note the volume path, which can differ between
   installations.
3. Read the files and collections listed above from that volume.
4. Verify with `python scripts/verify_manifest.py verify <local directory>`.

Checksums, not paths, are the contract. A reinstalled share with a different path still
verifies if the bytes match.
