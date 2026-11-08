"""What the API serves. Protocol section 21, and the console design's decisions 1 to 15.

Every numeric or boolean leaf here is a `Sourced`, so section 21.6 mark 1 is a property of the types
rather than something a gate hopes to find. Strings are structure: a well name, a date, an
operator-facing label.

Two shapes carry a rule in their constructor rather than in a checker.

`Money` refuses an amount without its assumption. Section 20.3 fixed that rule for the
post-mortem's currency figure, and section 21.6 mark 5 applies it to a display, which is the harder
case: a document can carry its caveat in the next sentence, and a dashboard tile has no next
sentence. So the two cannot be separated in the payload at all, and a tile that renders the amount
has the assumption in the same object.

`Absence` makes "nothing found" an object with its own id. Section 21.3: a conclusion drawn from
nothing looks identical to a conclusion drawn from something unless the nothing is recorded, and a
blank cell in an evidence matrix is the most natural way to lose that distinction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from volve_ops.console.sources import Sourced


class Money(BaseModel):
    """An estimated currency figure, inseparable from the assumption it rests on.

    `amount` is None whenever no assumption was supplied, which is every run of this project so far:
    a rig day rate and an oil price are commercial figures it has no access to. The tile then shows
    `reason` instead of a number, which is the honest rendering and not a degraded one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Sourced | None = None
    assumption: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _an_amount_needs_its_assumption(self) -> Money:
        if self.amount is not None and self.amount.value is not None and not self.assumption:
            raise ValueError(
                "a currency figure may not be served without its assumption; section 20.3's "
                "reasoning is that an illustration which circulates as a finding is the failure "
                "mode, and a dashboard tile has no next sentence to put the caveat in"
            )
        if self.amount is None and not self.reason:
            raise ValueError("a money tile with no amount must say why, or it reads as a bug")
        return self


class Absence(BaseModel):
    """A recorded search that found nothing. Section 21.3.

    Not a blank cell. The corpus searched, the filters, the queries issued and the count examined,
    so that a reader can tell "looked and found nothing" from "did not look", and so that the cell
    lowers confidence rather than silently leaving it alone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    absence_id: str
    corpus: str
    filters: tuple[str, ...]
    queries: tuple[str, ...]
    documents_examined: Sourced
    outcome: Literal["none_found", "reason_not_documented"]


class FactEvidence(BaseModel):
    """The evidence drawer for a fact, from the console design's decision 7."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    metric: str
    baseline_value: Sourced
    episode_value: Sourced
    baseline_window: str
    episode_window: str
    source_table: str
    transformation: str
    input_records: Sourced
    derived_facts: tuple[str, ...] = ()


class DocumentEvidence(BaseModel):
    """The evidence drawer for a cited span, from decision 7."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    source_type: str
    document: str
    report_date: str
    span: str
    start_offset: Sourced
    end_offset: Sourced
    document_hash: str


class MatrixCell(BaseModel):
    """One hypothesis against one evidence family, and the rule that judged it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["supports", "contradicts", "neutral", "absent", "not_applicable"]
    label: str
    rule: str
    fact: FactEvidence | None = None
    document: DocumentEvidence | None = None
    absence: Absence | None = None

    @model_validator(mode="after")
    def _a_judged_cell_shows_its_object(self) -> MatrixCell:
        if self.verdict in {"supports", "contradicts"} and not (self.fact or self.document):
            raise ValueError(
                f"a {self.verdict!r} cell has to name the object it rests on; decision 7 makes "
                "every non-empty cell open a drawer, and a cell with nothing behind it is the "
                "unsourced figure of section 21.6 mark 1 in a different shape"
            )
        if self.verdict == "absent" and self.absence is None:
            raise ValueError(
                "an absent cell carries its retrieval record; section 21.3 stores absence as an "
                "object so that a reader can tell it from a cell nobody filled in"
            )
        return self


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    label: str
    status: str
    status_label: str
    cells: dict[str, MatrixCell]


class EvidenceCoverage(BaseModel):
    """Section 21.4's two lists, which are the whole of the abstention screen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: tuple[str, ...]
    missing: tuple[str, ...]


class ExpectationPanel(BaseModel):
    """How the expected line was built, from decision 8.

    The operator has to be able to see where the expectation came from, because every investigation
    rests on it. The box says the model is deterministic and fitted before the agent ran, which is
    the one claim about this system that an operator most needs to be able to check.
    """

    # `protected_namespaces=()` because the expectation model's own fields are `model_name` and
    # `model_version`, which pydantic reserves by default. Renaming them to suit the library would
    # make the payload disagree with `FittedExpectation`, which is the thing being described.
    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_name: str
    model_version: str
    reference_window: str
    regime: str
    backtest_wape: Sourced
    interval_coverage: Sourced
    note: str


class SeriesRow(BaseModel):
    """One day of the chart. Dates and classes are structure; the figures are sourced once per
    series rather than per point, because a per-point source would repeat one answer 2,117 times.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: str
    day_class: str
    actual: float | None
    expected: float | None
    lower: float | None
    upper: float | None
    below_band: bool
    on_stream_hours: float | None
    choke_size: float | None
    downhole_pressure_bar: float | None
    wellhead_pressure_bar: float | None
    water_cut: float | None


class ChartSeries(BaseModel):
    """The chart's rows, with one source for the lot and the row count as a sourced figure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    rows: tuple[SeriesRow, ...]
    row_count: Sourced
    episode_window: str
    governing_window: str


class QueueRow(BaseModel):
    """One line of the investigation queue, from decision 9."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    investigation_id: str
    well: str
    period: str
    actual_rate: Sourced
    expected_rate: Sourced
    cumulative_shortfall: Sourced
    deferred_volume: Sourced
    episode_days: Sourced
    assessment: str
    assessment_label: str
    causal_level_label: str
    evidence_strength: str
    review_state: str
    data_quality: str
    priority: str
    priority_score: Sourced
    priority_explanation: str


class PriorityRule(BaseModel):
    """The rule, printed under the table with what it fired on. Section 21.5 and ADR 0009."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    statement: tuple[str, ...]
    term_counts: dict[str, Sourced]
    caveat: str


class Kpi(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    figure: Sourced | None = None
    money: Money | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _a_tile_shows_one_thing(self) -> Kpi:
        if (self.figure is None) == (self.money is None):
            raise ValueError("a KPI tile carries exactly one of a figure or a money estimate")
        return self


class Header(BaseModel):
    """Decision 12: operational and data state first, build metadata behind a popover."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    mode: str
    data_through: str
    production_availability: str
    report_index_availability: str
    pressure_coverage: str
    posture: str
    build_info: dict[str, str]


class InvestigationDetail(BaseModel):
    """The signature screen, from decision 4."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    investigation_id: str
    well: str
    period: str
    assessment_label: str
    causal_level_label: str
    narrative: str
    what_would_change_the_conclusion: str
    recommended_next_check: str
    chart: ChartSeries
    expectation: ExpectationPanel
    hypotheses: tuple[Hypothesis, ...]
    evidence_families: tuple[str, ...]
    coverage: EvidenceCoverage
    review_disclaimer: str
    review_actions: dict[str, str]
    provenance: dict[str, str]


class Queue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kpis: tuple[Kpi, ...]
    rows: tuple[QueueRow, ...]
    rule: PriorityRule
    pinned: tuple[str, ...]
