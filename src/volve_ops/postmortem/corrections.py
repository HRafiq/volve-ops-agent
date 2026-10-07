"""The versioned correction store of protocol section 20.5.

Three rules, and the first is the one that matters: **a correction naming a hold-out event is
refused
when it is written, not flagged when it is audited.** Section 19.2's fourth leakage check audits
this
store and has examined nothing until now, because no store existed. It stops being vacuous here. But
an
audit runs after the fact, and after the fact the correction is already on disk and already in
whatever
the person was about to do with it. So the store refuses first and the audit confirms.

The second rule is append-only versioning, for the same reason the event store has it: a version
whose
contents can change describes something other than the run that cited it.

The third is the leakage rule from the plan, and it is the one that can only be half enforced. A
correction may become a few-shot example only in an extraction version later than the one that
produced
the event it corrects, otherwise a model is shown the answer to a question it is about to be asked.
The
store records which extractor version each correction was made against, and `examples_for` refuses
any
correction made against the version doing the asking. What cannot be enforced here is a person
pasting a
correction into a prompt by hand, and section 20.5 says so rather than implying the guarantee is
total.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Iterable, Sequence
from enum import StrEnum
from pathlib import Path

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


class HoldOutCorrectionRefused(Exception):
    """A correction named an event on a hold-out well. Section 20.5 rule 1."""


class StoreVersionExists(Exception):
    """A store version already has contents. Section 20.5 rule 2."""


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


def is_hold_out(well: str) -> bool:
    """Whether this well is held out under section 16, failing closed on a name it cannot parse.

    The same reasoning as the leakage audit: a gate that raises on input it does not recognise can
    be
    made to pass by breaking its input, and the cost of a false positive here is a refused
    correction
    while the cost of a false negative is a hold-out event in the store.
    """
    if well in HOLD_OUT_WELLS:
        return True
    try:
        return well_of(well) in HOLD_OUT_WELLS
    except UnresolvedWellName:
        return any(well.startswith(h + " ") for h in HOLD_OUT_WELLS)


class CorrectionStore:
    """An append-only directory of correction versions, one JSON-lines file each."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, version: str) -> Path:
        return self.root / f"{version}.jsonl"

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

    def write(self, version: str, corrections: Sequence[Correction]) -> Path:
        """Write a new version, refusing a hold-out correction and refusing to overwrite.

        Both refusals happen before anything touches the disk: a store that writes six corrections
        and
        then raises on the seventh has already leaked the hold-out event in the first six.
        """
        offending = [c for c in corrections if is_hold_out(c.well)]
        if offending:
            raise HoldOutCorrectionRefused(
                f"{len(offending)} correction(s) name hold-out wells "
                f"{sorted({c.well for c in offending})}; section 16 reserves them for Phase 8, and "
                "section 20.5 refuses them here rather than flagging them at audit time"
            )
        path = self._path(version)
        if path.exists() and path.read_text(encoding="utf-8").strip():
            raise StoreVersionExists(
                f"correction store version {version!r} already has contents; a version whose "
                "contents can change describes something other than the run that cited it"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(c.model_dump_json() + "\n" for c in corrections), encoding="utf-8")
        return path

    def examples_for(self, version: str, extractor_version: str) -> list[Correction]:
        """Corrections usable as few-shot examples by this extractor version.

        Section 20.5 rule 3. A correction made against the version doing the asking is withheld:
        using
        it would show a model the answer to a question it is about to be asked on the same events.
        """
        return [c for c in self.read(version) if c.extractor_version != extractor_version]

    def content_hash(self, version: str) -> str:
        """A digest over a version's corrections, order-independent.

        Order-independent so that a changed digest means changed content rather than a differently
        scheduled write, which is the same property the event store's hash has.
        """
        digests = sorted(
            hashlib.sha256(c.model_dump_json().encode()).hexdigest() for c in self.read(version)
        )
        return hashlib.sha256("".join(digests).encode()).hexdigest()[:16]


def propose(
    event: NPTEvent,
    field: CorrectionField,
    new_value: str,
    *,
    corrected_by: str,
    note: str | None = None,
) -> Correction:
    """Build a correction from the event it corrects, so the old value cannot be mistyped."""
    old = {
        CorrectionField.CATEGORY: event.activity_code,
        CorrectionField.DURATION: f"{event.duration_hours}",
        CorrectionField.EQUIPMENT: event.equipment or "",
        CorrectionField.CAUSE_TEXT: event.comment,
    }[field]
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
    """The shape section 19.2's fourth leakage check reads, so the audit needs no adapter."""
    return [json.loads(c.model_dump_json()) for c in corrections]
