"""The versioned correction store of protocol section 20.5.

Three rules, and the first is the one that matters: **a correction naming a hold-out event is
refused when it is written, not flagged when it is audited.** An audit runs after the fact, and by
then the correction is on disk and already in whatever the person was about to do with it. So the
store refuses first and the audit confirms.

Section 19.2's fourth leakage check audits this store and **still examines nothing**, because the
store is empty: a correction is a person changing a value and no person has changed one. An earlier
version of this docstring promised the check would stop being vacuous here, which section 20.5
promised too and which did not happen. Protocol amendment 8 withdraws the promise in both places
rather than restating it. What exists instead is a demonstrated refusal, probed on every run.

The second rule is append-only versioning, for the same reason the event store has it: a version
whose contents can change describes something other than the run that cited it.

The third is the leakage rule from the plan, and it is the one that can only be half enforced. A
correction may become a few-shot example only in an extraction version later than the one that
produced the event it corrects, otherwise a model is shown the answer to a question it is about to
be asked. The store records which extractor version each correction was made against, and
`examples_for` refuses any correction made against the version doing the asking. What cannot be
enforced here is a person pasting a correction into a prompt by hand, and section 20.5 says so
rather than implying the guarantee is total.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.well_naming import UnresolvedWellName, well_of
from volve_ops.extraction.npt import NPTEvent
from volve_ops.extraction.sampling import HOLD_OUT_WELLS


class CorrectionField(StrEnum):
    """What a person may correct. The plan names these four and no others.

    Deliberately not the cause: a cause correction would be a label, and section 17 governs where
    labels come from and what they may be used for.
    """

    CATEGORY = "category"
    DURATION = "duration"
    EQUIPMENT = "equipment"
    CAUSE_TEXT = "cause_text"


#: A version name must be a plain identifier, so it cannot escape the store directory.
#: `store.write("../escaped", ...)` wrote to the store's parent, where `versions()` could not glob
#: it and the leakage audit could not read it: a correction could exist on disk and be structurally
#: invisible to the gate meant to find it.
_VERSION_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Development wells in the drilling-report corpus. Used only so that an unparseable name which is
#: clearly a development well is let through rather than refused, which keeps a typo in a
#: development well's name from reading as a hold-out leak.
DEVELOPMENT_WELLS: Final[tuple[str, ...]] = (
    "15/9-19",
    "15/9-F-1",
    "15/9-F-10",
    "15/9-F-11",
    "15/9-F-12",
    "15/9-F-14",
    "15/9-F-15",
)


class HoldOutCorrectionRefused(Exception):
    """A correction reached an event on a hold-out well. Section 20.5 rule 1."""


class BadVersionName(Exception):
    """A version name that is not an identifier, or that would escape the store directory."""


class StoreVersionExists(Exception):
    """A store version already has contents. Section 20.5 rule 2."""


class StoreVersionMissing(Exception):
    """A version was addressed that the store does not hold."""


class Correction(BaseModel):
    """One recorded change, with everything needed to audit it later."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    well: str
    field: CorrectionField
    old_value: str
    new_value: str
    corrected_by: str
    corrected_at: str
    extractor_version: str
    note: str | None = None


def _bare(name: str) -> str:
    return re.sub(r"[^A-Z0-9/-]", "", _ascii_digits(name).upper())


def _ascii_digits(text: str) -> str:
    """Fold any Unicode decimal digit onto its ASCII form.

    `well_of` *succeeds* on a name whose final digit is the full-width form U+FF14, returning it
    unchanged, so the resolver branch answered False before the fail-closed fallback could be
    reached. A name a person could paste out of a spreadsheet is the expected input here.
    """
    return "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in text)


def _without_leading_zeros(text: str) -> str:
    """Strip leading zeros from each run of digits: `15/9-F-04` becomes `15/9-F-4`.

    `well_of` resolves the padded spelling to itself, so it is in neither well list and the
    resolver branch answered False before the fail-closed fallback could run. Applied only as an
    extra candidate, never to the name a figure is published under.
    """
    return re.sub(r"0+(\d)", r"\1", text)


def is_hold_out(well: str) -> bool:
    """Whether this well is held out under section 16, failing **closed** on an unparseable name.

    The first version claimed to fail closed and failed open. `well_of` raises on `15/9-f-4`, on the
    NPD spelling `NO 15/9-F-4` and on `15 / 9-F-4`, and the fallback then answered False for all
    three. Review found it, and this is a correction store: the well name is typed by a person, so
    unparseable input is the expected case rather than the exotic one.

    So the resolver is tried, then tried again on a normalised form, and a name that still will not
    parse is refused unless it is recognisably a development well. A false positive costs a refused
    correction and a sentence of explanation; a false negative puts a hold-out event into a store
    that a scored run cites.
    """
    if well in HOLD_OUT_WELLS:
        return True
    normalised = re.sub(r"\s+", " ", _ascii_digits(well).strip().upper()).removeprefix("NO ")
    # Every reading that resolves, not the first one. Returning on the first success let a
    # full-width final digit answer False: `well_of` accepts it and hands the same string back, so
    # the raw form resolved to a well in neither list and the normalised form was never tried. If
    # any reading of the name lands on a hold-out well, the correction is refused.
    resolved: list[str] = []
    for candidate in (well, normalised, _without_leading_zeros(normalised)):
        try:
            resolved.append(well_of(candidate))
        except UnresolvedWellName:
            continue
    if resolved:
        # A resolved name is decided on the resolution alone, so the prefix fallback below never
        # overrides it: running it unconditionally made `15/9-F-50`, `15/9-F-5X` and `15/9-F-40`
        # read as hold-out wells.
        return any(name in HOLD_OUT_WELLS for name in resolved)
    stripped = _bare(normalised)
    if any(stripped.startswith(_bare(h)) for h in HOLD_OUT_WELLS):
        return True
    return not any(stripped.startswith(_bare(d)) for d in DEVELOPMENT_WELLS)


#: A version name's ordinal suffix: a separator or the string start, a `v`, digits, and then the
#: end. `re.search(r"v(\d+)")` matched anywhere, so `extractor-dev2` read as 2, `prev3-extractor` as
#: 3 and `extractor-rev9-v1` as 9. The last is the one that leaks: an extractor at v1 read as v9 is
#: served every correction made against v2 through v8, which is rule 3 running backwards in time.
#: The leading separator is what rules out `dev2`, and a leading zero is rejected rather than read,
#: because `v01` and `v1` naming one ordinal is a collision nothing else here would catch.
_VERSION_ORDINAL: Final = re.compile(r"(?:^|[^A-Za-z0-9])v(0|[1-9]\d*)$", re.IGNORECASE)

#: Leaves room for the `.jsonl` suffix inside the 255 bytes most filesystems allow a name.
_MAX_VERSION_NAME: Final[int] = 240


def _hold_out_text(correction: Correction) -> str | None:
    """The first hold-out well name quoted in a correction's free text, if any.

    Review's attack was a correction whose event id and well were both consistent and whose
    `old_value` carried a hold-out report's verbatim comment. The id and the well can be made
    honest; the text is where the hold-out actually travels, and a check that reads only the
    metadata does not see it.

    Two spellings are matched, over a haystack whose `_` and `.` are folded to `-` and whose
    whitespace is dropped: the canonical `15/9-F-4`, which covers `15/9-f-4` and `15 / 9-F-4`, and
    the hyphen form `15-9-F-4`, which covers the filename spelling `15_9_F_4_2008_01_01.xml`.

    **A digit may not follow the match.** Without that rule `15/9-F-40` and `15/9-F-50` were refused
    for naming `15/9-F-4` and `15/9-F-5`. Over-refusal is the safe direction here, but refusing a
    correction about `15/9-F-40` because `15/9-F-4` is a prefix of it is a defect and not caution:
    they are different wells and only one is held out. (A review noted that `159F40`, cited in an
    earlier version of this paragraph, never matched either way, because neither needle survives the
    loss of its separators. The two well spellings are what the rule is load-bearing for.)

    What this does not catch is a name written with no separators at all, or paraphrased, or
    translated. A textual guard cannot stop someone determined to evade it; this one is here for the
    realistic case, which is a span pasted out of a report, and section 20.5 says so rather than
    implying the guarantee is total.
    """
    text = " ".join(
        filter(
            None,
            (correction.old_value, correction.new_value, correction.note, correction.corrected_by),
        )
    )
    haystack = _bare(text.replace("_", "-").replace(".", "-"))
    for well in HOLD_OUT_WELLS:
        bare = _bare(well)
        if _mentions(haystack, bare) or _mentions(haystack, bare.replace("/", "-")):
            return well
    return None


def _mentions(haystack: str, needle: str) -> bool:
    """Whether `needle` appears in `haystack` without a digit immediately after it."""
    start = haystack.find(needle)
    while start != -1:
        after = start + len(needle)
        if after >= len(haystack) or not haystack[after].isdigit():
            return True
        start = haystack.find(needle, start + 1)
    return False


def _ordinal(version: str) -> int | None:
    """The numeric part of an extractor version, or None when it cannot be read.

    `extractor-v0` is 0. Anything unparseable returns None, and `examples_for` withholds rather than
    serves in that case, because defaulting to serve is the direction that leaks.
    """
    match = _VERSION_ORDINAL.search(version.strip())
    return int(match.group(1)) if match else None


class CorrectionStore:
    """An append-only directory of correction versions, one JSON-lines file each."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, version: str) -> Path:
        if not _VERSION_NAME.match(version):
            raise BadVersionName(
                f"{version!r} is not a version name; it must match "
                f"{_VERSION_NAME.pattern} so that it cannot escape the store directory"
            )
        if len(version) > _MAX_VERSION_NAME:
            raise BadVersionName(
                f"a version name of {len(version)} characters is refused at "
                f"{_MAX_VERSION_NAME}; past that the filesystem raises `OSError` and the caller "
                "cannot tell a bad name from a full disk"
            )
        path = (self.root / f"{version}.jsonl").resolve()
        if path.parent != self.root.resolve():
            raise BadVersionName(f"{version!r} resolves outside the store directory")
        return path

    def versions(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.jsonl")) if self.root.exists() else []

    def read(self, version: str) -> list[Correction]:
        path = self._path(version)
        if not path.exists():
            return []
        return [
            Correction.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def write(
        self,
        version: str,
        rows: Sequence[Correction],
        events: Mapping[str, NPTEvent],
    ) -> Path:
        """Write a new version, refusing a hold-out correction and refusing to overwrite.

        Every refusal happens before anything touches the disk: a store that writes six corrections
        and then raises on the seventh has already leaked the first six.

        `events` maps event id to the event, and is **required**. It began as an optional mapping of
        id to well, which review showed no caller supplied, so the only path anything exercised was
        the forgeable fallback it had been added to replace. It is the whole event now rather than
        the well, because of what a fourth review measured.

        **Five refusals, and the fourth is the one that actually closes the attack.**

        1. An event this store was given nothing for is refused. Failing closed, because an
           unplaceable event id is what a forged one looks like.
        2. An event whose well disagrees with the correction's well is refused.
        3. A hold-out well on either side is refused.
        4. **A correction whose old value is not what the record says for that field is refused.**
           The attack is a correction carrying a hold-out report's verbatim comment under an honest
           development event id and well, and this is what sees it: that comment is not the
           development event's comment, so the correction is not a correction of that event.
           `propose` fills the old value in from the event for the same reason, and both now read
           `recorded_value`, so there is one definition of what the record says.
        5. Hold-out text in the free-text fields, which is a **weak** guard and is kept as one. A
           fourth review measured it: the short form a comment actually uses, `F-4`, appears in only
           18 of this corpus's 616 hold-out comments, 2.9 percent, because a report about a well
           mostly does not name the well. Matching it also refuses 15 of 3,057 development comments,
           0.5 percent, which legitimately mention a neighbour. So rule 5 catches the obvious paste
           and nothing else; rule 4 is what makes the guarantee. Section 20.5 publishes both numbers
           rather than implying the scan is a gate.
        """
        known = dict(events)
        offending: dict[str, str] = {}
        for correction in rows:
            event = known.get(correction.event_id)
            if event is None:
                raise HoldOutCorrectionRefused(
                    f"{correction.event_id!r} is not an event this store was given; a correction "
                    "whose event cannot be placed is refused rather than trusted, because an "
                    "unplaceable event id is what a forged one looks like"
                )
            if event.well != correction.well:
                raise HoldOutCorrectionRefused(
                    f"{correction.event_id} belongs to {event.well!r} and the correction claims "
                    f"{correction.well!r}; a disagreement there is how a hold-out event is "
                    "smuggled past a check that reads the well"
                )
            if is_hold_out(event.well) or is_hold_out(correction.well):
                offending[correction.event_id] = event.well
            current = recorded_value(event, correction.field)
            if correction.old_value != current:
                raise HoldOutCorrectionRefused(
                    f"{correction.event_id}: the old {correction.field.value} is not what the "
                    f"record says ({current[:60]!r}); a correction whose old value belongs to a "
                    "different event is not a correction of this one, and that is how a hold-out "
                    "report's text travels under an honest event id"
                )
            quoted = _hold_out_text(correction)
            if quoted:
                raise HoldOutCorrectionRefused(
                    f"{correction.event_id} quotes {quoted!r}, a hold-out well, in its text; "
                    "section 16 reserves those reports for Phase 8 and a verbatim span carries "
                    "them as surely as an event id does"
                )
        if offending:
            raise HoldOutCorrectionRefused(
                f"{len(offending)} correction(s) reach hold-out wells "
                f"{sorted(set(offending.values()))}; section 16 reserves them for Phase 8, and "
                "section 20.5 refuses them here rather than flagging them at audit time"
            )
        path = self._path(version)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            # `x` so the filesystem enforces it. Testing `exists() and read_text().strip()` let an
            # empty version be created and then filled, so a run could cite a version holding
            # nothing and that version could later hold a correction.
            with path.open("x", encoding="utf-8") as handle:
                handle.write("".join(c.model_dump_json() + "\n" for c in rows))
        except FileExistsError as exc:
            raise StoreVersionExists(
                f"correction store version {version!r} already exists; a version whose contents "
                "can change describes something other than the run that cited it"
            ) from exc
        return path

    def examples_for(self, version: str, extractor_version: str) -> list[Correction]:
        """Corrections usable as few-shot examples by this extractor version.

        Section 20.5 rule 3 says **later**, not merely different, and the first version compared for
        inequality: a correction made against `extractor-v3` was served to `extractor-v0`. Ordinals
        are compared instead, and an unparseable version on either side is withheld.
        """
        asking = _ordinal(extractor_version)
        usable: list[Correction] = []
        for correction in self.read(version):
            made_against = _ordinal(correction.extractor_version)
            if asking is None or made_against is None:
                continue
            if made_against < asking:
                usable.append(correction)
        return usable

    def content_hash(self, version: str) -> str:
        """A digest over a version's corrections, order-independent.

        Order-independent so that a changed digest means changed content rather than a differently
        scheduled write, which is the same property the event store's hash has.

        Raises on a version that does not exist. The first implementation hashed the empty read and
        returned `sha256("")`, which is indistinguishable from the digest of a version that exists
        and holds nothing, so a run could cite a hash for a version it had never written.
        """
        path = self._path(version)
        if not path.exists():
            raise StoreVersionMissing(
                f"correction store version {version!r} does not exist; hashing it would return the "
                "digest of an empty version, which is a different claim"
            )
        digests = sorted(
            hashlib.sha256(c.model_dump_json().encode()).hexdigest() for c in self.read(version)
        )
        return hashlib.sha256("".join(digests).encode()).hexdigest()[:16]


def recorded_value(event: NPTEvent, field: CorrectionField) -> str:
    """What the record currently says for this field. The one definition of "the old value".

    Shared by `propose`, which fills it in, and `CorrectionStore.write`, which refuses a correction
    whose old value disagrees with it. That refusal is what closes the attack the text scan cannot:
    a correction carrying another event's comment is not a correction of this event, whatever its
    metadata says, and no textual guard is needed to see it.
    """
    return {
        CorrectionField.CATEGORY: event.activity_code,
        CorrectionField.DURATION: f"{event.duration_hours}",
        CorrectionField.EQUIPMENT: event.equipment or "",
        CorrectionField.CAUSE_TEXT: event.comment,
    }[field]


def propose(
    event: NPTEvent,
    field: CorrectionField,
    new_value: str,
    *,
    corrected_by: str,
    note: str | None = None,
) -> Correction:
    """Build a correction from the event it corrects, so the old value cannot be mistyped."""
    old = recorded_value(event, field)
    return Correction(
        event_id=event.event_id,
        well=event.well,
        field=field,
        old_value=old,
        new_value=new_value,
        corrected_by=corrected_by,
        corrected_at=dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        extractor_version=event.extractor_version,
        note=note,
    )


def as_audit_rows(corrections: Iterable[Correction]) -> list[dict[str, object]]:
    """The shape section 19.2's fourth leakage check reads.

    Called by `scripts/run_evaluation.py`. Review found this written with no call site at all while
    section 20.5 claimed the check had stopped being vacuous, so the adapter existed and the audit
    it was written for was never given anything.
    """
    return [json.loads(c.model_dump_json()) for c in corrections]
