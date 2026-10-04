# Data profile

What the dataset actually contains, measured rather than assumed. Figures here come from the
files named in `docs/data_manifest.md` and are reproducible from them.

Raw data is never committed, so this document and the manifest are what a reader gets instead.

## How the data is accessed

Equinor distributes the Volve dataset through a data marketplace share rather than a download.
The share installs into a catalog volume, and this project reads selected files from it over
the files API. The share totals roughly 5 TB, almost all of it seismic and reservoir models,
none of which this project reads.

What is read is small. The production workbook is 2.3 MB and the full daily drilling report
corpus is 21.3 MB, so the working set is cached locally and every analysis after the first runs
offline.

A share installation is removed automatically after 90 days and has to be reinstalled, which
can change the volume path. Checksums rather than paths are what tie a result to its inputs.

## Production data

One workbook, two sheets, covering 1 September 2007 to 1 December 2016.

The daily sheet has 15,634 rows over 24 columns and seven wellbores. Of those, six are oil
producers and three are water injectors; two wellbores appear under both roles at different
times.

Valid producing days, under the definition fixed in `docs/eval_protocol.md` section 6, which
requires at least 6.0 on-stream hours, a recorded oil volume, and production status:

| wellbore | valid producing days | first | last |
|---|---:|---|---|
| 15/9-F-12 | 2,793 | 2008-02-12 | 2016-08-12 |
| 15/9-F-14 | 2,683 | 2008-07-13 | 2016-07-13 |
| 15/9-F-11 | 1,107 | 2013-07-24 | 2016-09-17 |
| 15/9-F-15 D | 764 | 2014-01-16 | 2016-07-06 |
| 15/9-F-1 C | 427 | 2014-04-21 | 2016-04-06 |
| 15/9-F-5 | 120 | 2016-04-21 | 2016-08-26 |

Total 7,894 valid producing days across six producers.

### Measurement coverage

Missingness is substantial and uneven. Across all 15,634 daily rows, the oil, gas and water
volumes are absent in 6,473, downhole pressure and temperature in 6,654, annulus pressure in
7,744, choke size in 6,715, and water injection volume in 9,928. Much of that is structural:
an injector row has no production volume. On-stream hours are absent in 285 rows and recorded
as zero in 1,952.

Choke is recorded as percent open; the unit column carries a single value and is itself absent
in 6,473 rows.

### What the pre-registered physical checks found

Each of these rules was fixed before any file was opened. On producer rows:

| check | rows |
|---|---:|
| on-stream hours above 24 | 13, up to 25.0 |
| negative volume | 4, water to −457.84 |
| oil volume on a zero-hour day | 1 |
| zero oil with hours above zero | 13 |
| of those, with no gas and no water either | 12 |
| duplicate well-days | 0 |

The last two rows are the ones that matter. Twelve of the thirteen zero-oil days have nothing
corroborating them and are quarantined as probable recording gaps. One has measurable gas or
water and survives as a genuine producing day that made no oil, which is a real
underperformance signal. Without that distinction all thirteen would have been read as severe
underperformance.

### Temporal split

Applying section 10 of the protocol mechanically, the production record runs from 12 February
2008 to 17 September 2016, a span of 3,140 days. The hold-out boundary falls at 25 July 2014
and development data ends at 26 April 2014 after the 90-day buffer.

| wellbore | development days | hold-out days | status |
|---|---:|---:|---|
| 15/9-F-12 | 2,016 | 699 | retained |
| 15/9-F-14 | 1,886 | 708 | retained |
| 15/9-F-11 | 256 | 761 | retained |
| 15/9-F-15 D | 97 | 577 | cold start, excluded |
| 15/9-F-1 C | 5 | 333 | cold start, excluded |
| 15/9-F-5 | 0 | 120 | cold start, excluded |

Three of six producers survive the 150-day rule. The protocol's clause triggers on fewer than
half, and three is not fewer than three, so the hold-out stands on 2,168 valid producing days
from three wells. It passes by one well, and that should be read as a limitation rather than a
margin. Half the field came online in 2014, so a temporal split necessarily puts the later
wells almost entirely on the hold-out side.

## Daily drilling reports

1,759 reports, one per well-day, in WITSML `drillReport` form against a national regulator's
profiled schema, totalling 21.3 MB. The same reports are also published as HTML and PDF. They
cover 26 wells and wellbores, from 1992 to 2018.

Each report carries a sequence of activity blocks, 23,447 in total and 13.3 per report on
average. Each block has start and end timestamps, a two-level activity code, a state of ok or
fail, a detail state, and a free-text comment. The activity code separates drilling,
completion, workover, plug and abandon, moving and interruption, and at the second level
distinguishes causes such as waiting on weather and maintenance.

Reports also carry well and wellbore aliases with an explicit naming system, including the
regulator's own codes. Canonicalisation can therefore be driven from the data rather than
inferred from directory names, which is necessary because the directory naming is inconsistent:
26 wellbore directories appear under four different operator prefixes, with the slash in a well
name encoded as `$47$`.

Hole size is recorded on most but not all days. Between 5% and 34% of drilling days per well
carry no hole size, which limits any analysis that depends on attributing time to a hole
section.

## Documents

Per-well engineering documents, mostly PDF with some Word files:

| kind | files | wells |
|---|---:|---:|
| completion report | 26 | 16 |
| drilling programme | 25 | 13 |
| end of well report | 19 | 17 |
| completion log | 12 | 11 |
| geosteering | 8 | 3 |
| final well report | 2 | 2 |

Quality is uneven. Some are machine-readable text; at least one drilling programme extracts as
four characters, meaning it is a scanned image. A handful of entries are Windows shortcut files
pointing at documents that are not in the share.

Two field-level documents sit outside the per-well structure: a discovery report of 182 MB and
a development plan of 4.8 MB.

## Realtime drilling data

11,151 WITSML message objects plus smaller counts of bhaRun, tubular, trajectory, log,
wellbore geometry, rig and mudlog objects. The messages are terse operational notes: median 18
characters, 90% under 40, longest observed 127. They are an event stream rather than a
narrative record.

Every message sampled carried audit metadata identifying a named account and an internal
network address. ADR 0006 records that those fields are dropped at ingest.

## Limitations a reader should carry into the results

One field, six oil producers, and a production record where half the wells came online in the
final third of it.

The hold-out rests on three wells. Cross-well generalisation cannot be measured on a field this
size and is not claimed.

Non-productive time is identified from activity codes applied by the people writing the reports
at the time. Time that nobody coded as an interruption is invisible to this system, and no
claim is made to have found all of it.

Drilling plans exist for four wells but cover enough of only two, so planned-versus-actual
reporting is not built. ADR 0003 records the evidence.

No independent aggregate production series exists in the dataset, so allocation cannot be
reconciled. ADR 0004 records the evidence.
