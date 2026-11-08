"""Where a figure came from, carried by the figure itself. Protocol section 21.6 mark 1.

The mark says every figure in every API payload resolves to a manifest key or a fact id. A gate
could check that by walking a payload and looking numbers up, and that gate would be the shape this
project has had to fix five times: a check written beside the thing it checks, passing because the
thing happens to be right today.

So the payload type makes an unsourced figure **unconstructible**. A numeric or boolean leaf is a
`Sourced`, which cannot be built without a source string, and `unsourced_figures` walks a payload
looking for a bare number: finding one is a defect in the payload's shape rather than in its
contents. The gate then has two jobs, both narrow: no bare numbers anywhere, and every source
string actually resolves.

Strings are not figures, following section 19.3's rule that numeric and boolean leaves are the
published results and a label is not one. A well name, a verdict, a date and an operator-facing
label are structure; they are checked by other marks, not by this one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar, Final

from pydantic import BaseModel, ConfigDict, field_validator

from volve_ops.evaluation.table import locate

#: A fact id minted by the provenance ledger, or a document-evidence id. Both are citable objects
#: with their own lineage, so a figure sourced to one is traceable without a manifest key.
_FACT_ID: Final = re.compile(r"^(fact|derived|doc_ev|npt)_[A-Za-z0-9]+$")

#: The sentinel for a figure the console computes from nothing but other sourced figures and the
#: pre-registered rule that combines them. Used by the priority score and nowhere else.
#:
#: This is the one hole in mark 1 and it is declared rather than hidden. The priority score is not
#: in any manifest, because section 21.5 fixes the rule and the score is the rule applied to figures
#: that *are* in a manifest. Sourcing it to "rule:21.5" says exactly that, and `resolve_source`
#: accepts it only when the rule's own inputs were themselves sourced, which `assemble` enforces by
#: constructing the score from `Sourced` inputs.
RULE_PREFIX: Final[str] = "rule:"

#: The prefix for a figure read from a per-episode artifact rather than a run manifest. The artifact
#: is a file a harness wrote, so the source resolves by the file existing, and `resolve_source` is
#: given the directory to look in. Used for the chart series, whose rows are not in any manifest
#: because 109 days of ten channels is a record rather than a published figure.
ARTIFACT_PREFIX: Final[str] = "artifact:"


class UnsourcedFigure(Exception):
    """A payload carried a bare number. Section 21.6 mark 1."""


class SourcedTable(BaseModel):
    """A block of rows vouched for by one source, rather than per cell.

    The declared exemption to mark 1, and protocol amendment 10 records why it exists. The chart on
    an investigation screen is 109 days of ten channels: 1,090 numbers, every one of them from the
    same artifact, written by the same harness, in one pass. Wrapping each in a `Sourced` would
    repeat one answer a thousand times and make the payload unreadable, and mark 1's purpose is that
    a reader can ask where a number came from, not that the answer be restated beside each one.

    What keeps the exemption honest is `row_count`. The walker does not descend into these rows, so
    the gate checks instead that the count the table publishes equals the rows it actually carries.
    A table cannot then vouch for rows it does not have, and the one number that bounds the
    exemption is itself a `Sourced` that has to resolve.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    row_count: Sourced

    #: Which field holds the rows. Declared rather than discovered, because `actual_rows` used to
    #: return the length of the **first** list-shaped field it met: a subclass declaring any other
    #: list before `rows` had its count checked against the wrong one, and 7 rows went through under
    #: a declared count of 2.
    rows_field: ClassVar[str] = "rows"

    #: Fields a table may carry that are **records** rather than results. Amendment 10's third bound
    #: is the one nothing was checking: a daily rate is what the source says happened, and a
    #: shortfall, a share, a count or a score is a figure this project computed. A subclass declares
    #: which of its row fields are derived, and `derived_columns` is what the gate reads.
    derived_columns: ClassVar[frozenset[str]] = frozenset()

    def declared_rows(self) -> int:
        """The count the table publishes, or -1 when it publishes none.

        The sentinel is why `rows_mismatch` compares against `actual_rows` rather than letting two
        -1s cancel. A null `row_count` and a missing rows field both gave -1, so a table carrying
        unsourced floats in a dict with a null count passed the gate outright.
        """
        value = self.row_count.value
        return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else -1

    def actual_rows(self) -> int:
        rows = getattr(self, self.rows_field, None)
        return len(rows) if isinstance(rows, tuple | list) else -1

    def rows_mismatch(self) -> str | None:
        """Why this table's count cannot be trusted, or None when it can.

        Three ways to fail, and the first two were both passes before: a count that is not a number,
        a table with no rows field, and a count that disagrees with the rows present.
        """
        declared, actual = self.declared_rows(), self.actual_rows()
        if declared < 0:
            return (
                f"publishes no usable row count ({self.row_count.value!r}); the count is what "
                "bounds amendment 10's exemption, so a table without one is not exempt"
            )
        if actual < 0:
            return (
                f"declares its rows in {self.rows_field!r} and carries no such sequence; "
                "a table that vouches for rows it does not have is the failure the bound exists for"
            )
        if declared != actual:
            return f"claims {declared} rows and carries {actual}"
        return None


class Sourced(BaseModel):
    """One figure, with the manifest key or fact id it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float | int | bool | None
    source: str
    unit: str | None = None
    denominator: str | None = None

    @field_validator("source")
    @classmethod
    def _source_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "a figure needs a manifest key, a fact id or a section 21.5 rule reference; "
                "an empty source is how an invented number reaches a screen"
            )
        return value


def resolve_source(
    source: str,
    manifests: Mapping[str, Mapping[str, Any]],
    *,
    fact_ids: frozenset[str] = frozenset(),
    artifacts: Path | None = None,
) -> bool:
    """Whether this source names something that exists.

    Four kinds, and nothing else is accepted:

    - a dotted manifest path, resolved with the same `locate` the results table uses, so a key whose
      name contains dots resolves here exactly as it does there;
    - a fact, derived-fact or event id present in `fact_ids`, which the caller takes from the
      ledger and the event store rather than from the artifact that cites it;
    - an `artifact:` path to a file a harness wrote, resolved by the file existing;
    - a `rule:` reference to a pre-registered rule.
    """
    if source.startswith(RULE_PREFIX):
        return len(source) > len(RULE_PREFIX)
    if source.startswith(ARTIFACT_PREFIX):
        name = source[len(ARTIFACT_PREFIX) :]
        if artifacts is None or not name or "/" in name or ".." in name:
            return False
        return (artifacts / name).exists()
    if _FACT_ID.match(source):
        return source in fact_ids
    manifest, _, key = source.partition(".")
    if not key or manifest not in manifests:
        return False
    return locate(manifests[manifest], key)[1]


def unsourced_figures(payload: Any, path: str = "") -> list[str]:
    """Paths to numeric or boolean leaves that are not `Sourced`.

    Walks dicts, lists and Pydantic models. A `Sourced` is not descended into: its `value` is the
    figure and its `source` is the answer to where it came from, so recursing would report the
    figure it exists to vouch for.
    """
    found: list[str] = []
    if isinstance(payload, Sourced):
        return found
    if isinstance(payload, SourcedTable):
        # The declared exemption. `source` and `row_count` are still walked, so the table's own
        # figure is checked; its rows are not, and `tables_in` hands them to the gate instead.
        return unsourced_figures(payload.row_count, f"{path}.row_count" if path else "row_count")
    if isinstance(payload, BaseModel):
        for name, value in payload:
            found.extend(unsourced_figures(value, f"{path}.{name}" if path else name))
        return found
    if isinstance(payload, Mapping):
        for name, value in payload.items():
            found.extend(unsourced_figures(value, f"{path}.{name}" if path else str(name)))
        return found
    if isinstance(payload, str):
        return found
    if isinstance(payload, Sequence):
        for index, value in enumerate(payload):
            found.extend(unsourced_figures(value, f"{path}.{index}"))
        return found
    if isinstance(payload, bool | int | float):
        found.append(path or "<root>")
    return found


def tables_in(payload: Any) -> list[SourcedTable]:
    """Every `SourcedTable` in a payload, for the gate that checks their counts.

    Recurses **into** a table's rows rather than stopping at it. Returning early meant a table
    nested inside another table's rows was invisible to the gate, so a lying inner table could be
    smuggled past the bound by the outer one vouching for it.
    """
    found: list[SourcedTable] = []
    if isinstance(payload, Sourced):
        return found
    if isinstance(payload, SourcedTable):
        found.append(payload)
        for _, value in payload:
            found.extend(tables_in(value))
        return found
    if isinstance(payload, BaseModel):
        for _, value in payload:
            found.extend(tables_in(value))
        return found
    if isinstance(payload, Mapping):
        for value in payload.values():
            found.extend(tables_in(value))
        return found
    if isinstance(payload, str):
        return found
    if isinstance(payload, Sequence):
        for value in payload:
            found.extend(tables_in(value))
        return found
    return found


def sources_in(payload: Any) -> list[str]:
    """Every source string a payload carries, in walk order."""
    found: list[str] = []
    if isinstance(payload, Sourced):
        return [payload.source]
    if isinstance(payload, SourcedTable):
        # The table's own two sources, **and** anything sourced inside its rows. Returning only the
        # first two meant a `Sourced` with an unresolvable source inside a row was invisible to
        # mark 1: the exemption is from per-cell sourcing, not from checking what is there.
        found = [payload.source, payload.row_count.source]
        for name, value in payload:
            if name not in {"source", "row_count"}:
                found.extend(sources_in(value))
        return found
    if isinstance(payload, BaseModel):
        for _, value in payload:
            found.extend(sources_in(value))
        return found
    if isinstance(payload, Mapping):
        for value in payload.values():
            found.extend(sources_in(value))
        return found
    if isinstance(payload, str):
        return found
    if isinstance(payload, Sequence):
        for value in payload:
            found.extend(sources_in(value))
        return found
    return found
