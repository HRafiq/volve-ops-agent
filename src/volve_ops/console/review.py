"""The human review log. Protocol section 21.6 mark 6, and the console design's decision 6.

Append-only, for the reason the event store and the correction store are append-only: a record that
can change describes something other than what happened. Here the stakes are specific. A confirmed
finding is a person putting their name to an assessment, and a system that let the assessment move
afterwards would have that person vouching for something they never read.

Four actions, and the wording matters as much as the mechanics. "Approve" is not one of them: the
design's decision 6 is that approving a finding could be read as approving an operational action,
and this system has no actuation path at all. The labels live in `labels.REVIEW_ACTION` and the
disclaimer is served with them, so the panel says in words that a review records a judgement of the
assessment and authorises nothing.

What each action does, and the last two are the ones a naive implementation gets wrong:

- **Confirm** records agreement. The finding is then immutable: a later confirm, dismissal or edit
  of the same finding is refused, because a finding cannot be both confirmed and something else.
- **Dismiss** records disagreement, and is equally final.
- **Add correction** does not edit the finding. It appends a correction record and increments the
  revision, so the finding keeps its text and the disagreement sits beside it rather than instead of
  it. Every later record carries the revision in force, which is how an auditor can tell a
  confirmation of the original from a confirmation of the twice-corrected version.
- **Request more evidence** does not re-run anything from here. It records a request, and a new
  investigation run is what satisfies it. Section 21.1 keeps the console out of the business of
  producing findings, and a console that could re-run one would be producing them.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

#: One file, JSON lines, appended to. The same shape as the correction store's versions, and for
#: the same reason: a reader with no tooling can see what happened in order.
DEFAULT_LOG: Final[Path] = Path("data/cache/review_log.jsonl")


class ReviewRefused(Exception):
    """An action the log will not record, with the reason in the message."""


class Action(StrEnum):
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    ADD_CORRECTION = "add_correction"


#: The two that settle a finding. After either, nothing else may be recorded against it.
SETTLING: Final[frozenset[Action]] = frozenset({Action.CONFIRM, Action.DISMISS})


class ReviewRecord(BaseModel):
    """One action by one person at one time, against one investigation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    investigation_id: str
    action: Action
    actor: str
    recorded_at: str
    note: str | None = None

    revision: int = 0
    """Which revision of the finding this action was recorded against, not a counter of corrections.

    A correction increments it; every other action carries the revision in force when it happened.
    So a confirmation recorded at revision 2 says the reviewer agreed with the finding **as
    corrected twice**, which is the question an auditor actually asks. Reading it as "how many
    corrections exist" gives the same number for a run of records and looks like a defect, so it is
    written down here rather than left to be inferred.
    """

    investigator_version: str
    protocol_version: str

    @field_validator("actor")
    @classmethod
    def _an_actor_is_named(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "a review record names the person who made it; an unattributed judgement is not a "
                "review, and decision 6 puts the reviewer's name on the record on purpose"
            )
        return value

    @field_validator("note")
    @classmethod
    def _a_correction_explains_itself(cls, value: str | None) -> str | None:
        return value


class ReviewLog:
    """Append-only review records for every investigation."""

    def __init__(self, path: Path = DEFAULT_LOG) -> None:
        self.path = path

    def read(self) -> list[ReviewRecord]:
        if not self.path.exists():
            return []
        return [
            ReviewRecord.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def for_investigation(self, investigation_id: str) -> list[ReviewRecord]:
        return [r for r in self.read() if r.investigation_id == investigation_id]

    def state_of(self, investigation_id: str) -> str:
        """The review state the queue shows. Derived from the log, never stored separately.

        A stored state and an append-only log would be two answers to one question, and the stored
        one would be the one that could drift.
        """
        records = self.for_investigation(investigation_id)
        if not records:
            return "none"
        for record in records:
            if record.action is Action.CONFIRM:
                return "confirmed"
            if record.action is Action.DISMISS:
                return "dismissed"
        if any(r.action is Action.REQUEST_MORE_EVIDENCE for r in records):
            return "rerun_requested"
        return "awaiting_review"

    def append(
        self,
        investigation_id: str,
        action: Action,
        *,
        actor: str,
        investigator_version: str,
        protocol_version: str,
        note: str | None = None,
        now: dt.datetime | None = None,
    ) -> ReviewRecord:
        """Record one action, refusing anything that would rewrite a settled finding."""
        existing = self.for_investigation(investigation_id)
        settled = [r for r in existing if r.action in SETTLING]
        if settled:
            raise ReviewRefused(
                f"{investigation_id} was already {settled[0].action.value}ed by "
                f"{settled[0].actor!r} at {settled[0].recorded_at}; a settled finding is "
                "immutable, because a person who confirmed an assessment cannot be made to vouch "
                "for a different one. Record a correction against it, or request a new run."
            )
        if action is Action.ADD_CORRECTION and not (note and note.strip()):
            raise ReviewRefused(
                "a correction has to say what is wrong; an empty correction is a disagreement "
                "nobody can act on and it would still lower the finding's standing"
            )
        moment = now or dt.datetime.now(tz=dt.UTC)
        revision = sum(1 for r in existing if r.action is Action.ADD_CORRECTION) + (
            1 if action is Action.ADD_CORRECTION else 0
        )
        record = ReviewRecord(
            investigation_id=investigation_id,
            action=action,
            actor=actor,
            recorded_at=moment.isoformat(timespec="seconds"),
            note=note,
            revision=revision,
            investigator_version=investigator_version,
            protocol_version=protocol_version,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
        return record


def as_rows(records: Iterable[ReviewRecord]) -> list[dict[str, object]]:
    """The shape the console shows, and the shape an audit reads."""
    return [json.loads(r.model_dump_json()) for r in records]


def pending(records: Sequence[ReviewRecord]) -> bool:
    """Whether a human action is outstanding, which is a term in section 21.5's priority rule."""
    return not any(r.action in SETTLING for r in records)
