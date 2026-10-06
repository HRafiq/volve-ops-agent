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
producers and two are water injectors, counted by the flow recorded on the day. One wellbore,
15/9-F-5, appears under both roles at different times, which is why those two counts sum to
eight rather than seven.

An earlier version of this document said three injectors and two dual-role wellbores. That came
from the well-type column rather than from the flow kind, and the two columns disagree on
eighteen rows. The reader that produces every other figure here classifies by flow kind, because
the day classification is about what the well did that day, so these counts now match it.

Valid producing days, under the definition fixed in `docs/eval_protocol.md` section 6, which
requires at least 6.0 on-stream hours, a recorded oil volume, production status, and no failed
physical check. These figures come from the implementation of that definition, not from a
filter that approximates it:

| wellbore | valid producing days | first | last |
|---|---:|---|---|
| 15/9-F-12 | 2,792 | 2008-02-12 | 2016-08-12 |
| 15/9-F-14 | 2,682 | 2008-07-13 | 2016-07-13 |
| 15/9-F-11 | 1,107 | 2013-07-24 | 2016-09-17 |
| 15/9-F-15 D | 762 | 2014-01-16 | 2016-07-06 |
| 15/9-F-1 C | 422 | 2014-04-22 | 2016-04-06 |
| 15/9-F-5 | 128 | 2016-04-21 | 2016-08-26 |

Total 7,893 valid producing days across six producers.

### Day classes over the whole daily sheet

| class | rows |
|---|---:|
| valid producing | 7,893 |
| non-producing | 6,181 |
| downtime | 1,140 |
| partial | 98 |
| quarantined | 37 |
| missing | 285 |

Non-producing is entirely injection: the source distinguishes only production from injection
flow, so nothing else can reach that class. Missing is 285 rows where on-stream hours were never
recorded, all of them on injectors, 152 on 15/9-F-4 and 133 on 15/9-F-5.

The source cannot express a shut-in producer. Its flow-kind column carries only production and
injection, so a producer that is shut in appears as a production-flow day with zero on-stream
hours and classes as downtime rather than non-producing. Downtime therefore includes shut-in
days, including the tail after a well stops producing for good: 15/9-F-14 has one unbroken
151-day downtime run, and every producer has downtime days after its own last valid producing
day. This does not reach any reported figure, because deferred volume is only summed inside an
episode window and such a window closes at the last valid producing day, but any future use of
downtime outside that context has to account for it.

### Measurement coverage

Missingness is substantial and uneven. Across all 15,634 daily rows, the oil, gas and water
volumes are absent in 6,473, downhole pressure and temperature in 6,654, annulus pressure in
7,744, choke size in 6,715, and water injection volume in 9,928. Much of that is structural:
an injector row has no production volume. On-stream hours are absent in 285 rows and recorded
as zero in 1,952.

Choke is recorded as percent open; the unit column carries a single value and is itself absent
in 6,473 rows.

### Two channels use zero to mean "no measurement", which a presence check misses

Counting non-empty cells overstates how much pressure data exists, by a lot. `AVG_DOWNHOLE_PRESSURE`
and `AVG_DOWNHOLE_TEMPERATURE` are recorded as `0.00` on 2,312 rows, all of them producer rows, and
1,924 of those record positive on-stream hours. A gauge three kilometres down cannot read 0 bar or 0
degrees Celsius, and a well cannot flow for hours at zero downhole pressure. The two channels are
zero on exactly the same rows, which is a paired gauge outage rather than two coincidences.

Usable coverage over the 9,161 producing well-days, where "usable" treats those zeros as absences
and takes every other channel at face value:

| channel | present | usable | sentinel zeros | usable share |
|---|---:|---:|---:|---:|
| on-stream hours | 9,161 | 9,161 | 0 | 100.0% |
| wellhead pressure | 9,155 | 9,155 | 0 | 99.9% |
| choke differential pressure | 9,155 | 9,155 | 0 | 99.9% |
| wellhead temperature | 9,146 | 9,146 | 0 | 99.8% |
| tubing differential pressure | 8,980 | 8,980 | 0 | 98.0% |
| choke size | 8,919 | 8,919 | 0 | 97.4% |
| annulus pressure | 7,890 | 7,890 | 0 | 86.1% |
| **downhole pressure** | 8,980 | **6,668** | 2,312 | **72.8%** |
| **downhole temperature** | 8,980 | **6,668** | 2,312 | **72.8%** |

Per well it is far more uneven than the total suggests, and it falls hardest on the well the
production results depend on most:

| wellbore | producing days | usable downhole pressure | sentinel zeros |
|---|---:|---:|---:|
| 15/9-F-15 D | 978 | 100.0% | 0 |
| 15/9-F-1 C | 746 | 99.3% | 2 |
| 15/9-F-11 | 1,165 | 98.2% | 15 |
| 15/9-F-14 | 3,056 | 93.3% | 200 |
| **15/9-F-12** | 3,056 | **31.2%** | 2,095 |
| **15/9-F-5** | 160 | **0.0%** | 0, the column is simply empty |

`15/9-F-12` is one of only two wells that reach the 150-day calibration gate and it carries most of
the detected episodes, so the well that matters most for production investigations has downhole
pressure on under a third of its producing days. A presence check would have reported 99.8% for it.
`15/9-F-5` has no downhole pressure at all.

This is why a pressure diagnostic cannot be a required input to an investigation. Protocol section
18 makes unavailable mandatory evidence an explicit stop condition and a published field of the
finding, rather than something an investigation works around silently. The judgement about which
zeros are absences lives in `src/volve_ops/domain/sensors.py`, in one place, with the five channels
it deliberately leaves alone.

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

### The on-stream hours are in local time, and it shows twice a year

All 20 rows with on-stream hours above 24, across every well, fall on the last Sunday of
October. That is the day European clocks go back, when a local day genuinely has 25 hours. The
figures are not corrupt; the column is wall-clock time on a local calendar, not elapsed time
against a 24-hour day.

The quarantine rule still fires on them, correctly, because a 25-hour day cannot be normalised
to a 24-hour rate without distorting it. The cost is that one day per well per year is set
aside, and a stable reference window containing one is disqualified under section 7.

The spring transition is the one that slips through. On the last Sunday of March a local day
has 23 hours, and 25 rows sit at exactly 23.0 on those dates, where a full day everywhere else
in the record is exactly 24.0. Sixteen of them class as valid producing days and pass every
check. For those, `q_24h` divides a whole day's oil by 23 and multiplies by 24, overstating the
rate by about 4.3 percent.

Sixteen days out of 7,893 is small, and it is left in place rather than fixed by another
post-inspection amendment to the protocol. It is recorded here because it is systematic rather
than random, it lands on the same calendar day each year, and anyone fitting a model to a window
containing one should know the uplift is an artifact of the clock and not of the well.

The last two rows of the table above are the ones that matter. Twelve of the thirteen zero-oil days have nothing
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
| 15/9-F-12 | 2,015 | 699 | retained |
| 15/9-F-14 | 1,885 | 708 | retained |
| 15/9-F-11 | 256 | 761 | retained |
| 15/9-F-15 D | 95 | 577 | cold start, excluded |
| 15/9-F-1 C | 4 | 328 | cold start, excluded |
| 15/9-F-5 | 0 | 128 | cold start, excluded |

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

The drilling-programme row counts every matching file across the 24 wellbore directories,
including Word documents and the same programme filed under several sidetracks of one well. Of
those, 18 are PDFs, and they span 8 distinct canonical wells. ADR 0003 works from that set of
18, which is why its count differs from the table.

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

## A correction, recorded rather than quietly applied

The valid-producing-day figures in an earlier version of this document were computed with a
spreadsheet filter rather than with the protocol's definition. That filter selected rows typed
as oil producers with on-stream hours between 6 and 24 inclusive and an oil volume present. It
reproduces the superseded 7,894 exactly, and the upper hours bound it used is itself one of the
section 7 quarantine rules, which is why the filter looked closer to the definition than it was.

Two independent differences, in opposite directions. Ten days the filter counted fail a
quarantine rule it did not apply: eight carry no oil, gas or water on a producing day, and two
carry a negative water volume. And eighteen rows where the source's flow-kind and well-type
columns disagree are now classed by the flow recorded on the day rather than by how the wellbore
is typed; nine of those become valid producing days and the other nine are downtime. The net is
minus ten plus nine, so the total moves from 7,894 to 7,893, and five of the six per-well
figures move.

Protocol v1 amendment 1 also applies to this document. Qualifying the missing test by status
moved 6,188 injector days out of the missing class: 6,181 into non-producing and 7 into
quarantined, the latter being injector rows that now reach the physical checks instead of
being short-circuited as missing. No row entered or left the three classes that carry an
expectation, so no production figure changed, which is what the amendment record demonstrates
rather than asserts.

## Limitations a reader should carry into the results

One field, six oil producers, and a production record where half the wells came online in the
final third of it.

The hold-out rests on three wells. Cross-well generalisation cannot be measured on a field this
size and is not claimed.

Well-name canonicalisation is not yet implemented. Section 6 of the protocol requires it to be
total, with wellbore and sidetrack relationships explicit or the row quarantined. The production
workbook uses one consistent naming system, so nothing here depends on it, but the drilling
reports use four different operator prefixes for the same wellbores and the join between the two
sources cannot be made until it exists.

Non-productive time is identified from activity codes applied by the people writing the reports
at the time. Time that nobody coded as an interruption is invisible to this system, and no
claim is made to have found all of it.

Drilling plans exist for four wells but cover enough of only two, so planned-versus-actual
reporting is not built. ADR 0003 records the evidence.

No independent aggregate production series exists in the dataset, so allocation cannot be
reconciled. ADR 0004 records the evidence.
