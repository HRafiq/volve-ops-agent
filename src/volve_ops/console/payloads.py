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

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from volve_ops.console.sources import Sourced, SourcedTable


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
    outcome: Literal["none_found", "reason_not_documented", "not_searched"]
    """What happened, and `not_searched` is the state the first version could not express.

    Section 21.3 exists so a reader can tell "looked and found nothing" from "did not look". The
    first implementation published `none_found` for both, with a query that was never issued and a
    hardcoded count of zero, on episodes where retrieval had returned citable documents. It lost the
    one distinction the section is about, in the only place the section is implemented.
    """


class LedgerFact(BaseModel):
    """One fact from the provenance ledger, with the value the ledger records.

    Its own value, which is the whole point. A first version of the drawer attached ledger ids to
    figures taken from somewhere else: `fact_000002` records a reference rate of 3,052.735 Sm3/d and
    the drawer published 4,351.41 Sm3/d under its id, a different quantity from the same manifest
    row. Independent review found all 198 fact-sourced leaves mis-attributed, 100 percent.

    Mark 1 could not see it, because the source resolved. That is the limit of "every figure
    resolves to a source" as a check: it asks whether the source exists, not whether the figure came
    from it. The fix is structural rather than another gate: a ledger fact now carries the ledger's
    value, so the two cannot be different numbers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    metric: str
    value: Sourced
    kind: str


class FactEvidence(BaseModel):
    """The evidence drawer for a figure, from the console design's decision 7."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str
    """What identifies this evidence. Not a ledger id unless the ledger defines it.

    For a hypothesis cell this is `<hypothesis>:<feature>`, because the figure that decided the cell
    is a strength feature the section 18.2 bundle computed and the ledger holds no fact for it.
    Labelling it with a ledger id was how the mis-attribution started.
    """

    metric: str
    value: Sourced
    baseline_value: Sourced
    episode_value: Sourced
    baseline_window: str
    episode_window: str
    source_table: str
    transformation: str
    ledger_facts: tuple[LedgerFact, ...] = ()


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

    lower_tail_rate: Sourced
    """How often the band is wrong on the side the detector uses.

    Named for what it is. It was `interval_coverage`, which is a different quantity: section 8 bands
    the lower-tail exceedance rate and reports two-sided coverage without a pass mark. The frontend
    labelled it correctly while the payload field did not, which is the kind of disagreement that
    survives until someone reads both.
    """

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


class ChartSeries(SourcedTable):
    """The chart's rows, with one source for the lot and the row count as a sourced figure.

    A `SourcedTable`, which is mark 1's declared exemption: 109 days of ten channels is 1,090
    numbers from one artifact, and a `Sourced` around each would repeat one answer a thousand times.
    `row_count` is what bounds the exemption, and the gate checks it against the rows actually here.

    **Four of the ten columns are results, not records**, and amendment 10's third bound says only
    a record may live in a table. `expected`, `lower` and `upper` are the output of the model
    section 7 selected, and `below_band` is the detector's comparison against it. Independent
    review found the bound violated by the exemption's only user, with nothing checking it.

    They are declared rather than removed, because a chart of actuals with no expectation is not the
    chart an operator needs and splitting them into 1,090 sourced figures is what the exemption
    exists to avoid. What the declaration buys is that the gate can see them: `derived_columns` is
    published, and amendment 11 narrows the bound to say a derived column must be declared and must
    come from the same artifact as the records beside it.
    """

    rows_field: ClassVar[str] = "rows"
    derived_columns: ClassVar[frozenset[str]] = frozenset(
        {"expected", "lower", "upper", "below_band"}
    )

    rows: tuple[SeriesRow, ...]
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
    """The log's own state, which is what the priority rule consumed.

    Carried raw alongside its label, the same way `assessment` and `assessment_label` are, because
    section 21.6 mark 8 recomputes each row's score from the printed rule and needs the value the
    rule was given. The harness previously fed the gate a hardcoded "none", so the gate agreed with
    the payload by construction on exactly the term that was broken.
    """

    review_state_label: str
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


# --------------------------------------------------------------------------------------------
# the System Health workspace, protocol section 22.4 marks 11 and 12
# --------------------------------------------------------------------------------------------


class ExpectationAblationRow(BaseModel):
    """One expectation model: how accurate it is, and how much work it creates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    episodes_opened: int
    wape: float | None


class ExpectationAblation(SourcedTable):
    """Section 22.7's first ablation, as a table of records under one source.

    `episodes_opened` and `wape` are both figures the ablation harness computed, so both are
    declared derived. Amendment 10's third bound: a result that rode into a table beside the
    records is what nothing was checking, and the only safe reading of a column this project
    calculated is that it is a result.
    """

    rows: tuple[ExpectationAblationRow, ...]
    derived_columns: ClassVar[frozenset[str]] = frozenset({"episodes_opened", "wape"})


class HealthRow(BaseModel):
    """One measured number on the health screen, with where it came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    value: Sourced
    note: str = ""


class VacuousInvariant(BaseModel):
    """An invariant with nothing to hold against here, and why.

    Rendered as its own list rather than mixed into the counts. Section 22.4 mark 1: an invariant
    that cannot be exercised is never added to a count of invariants preserved, and a screen that
    showed them together would undo in the display what the report structure prevents.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    wording: str
    reason: str


class NotApplicable(BaseModel):
    """A protection the design brief asks for that has nothing to protect here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    reason: str


class ComparisonRow(BaseModel):
    """One metric across two versions, and the delta only where a delta exists.

    **The delta is optional and `unavailable_because` is required when it is absent.** Section
    22.4 mark 12: where only one version exists there is nothing to subtract, and a 0.00 in a
    delta column against an absent baseline is a figure from nowhere, which section 21.2 forbids.
    It is also the most likely way this screen lies, because an empty column reads as no change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    current: Sourced
    previous: Sourced | None = None
    delta: Sourced | None = None
    unavailable_because: str = ""

    @model_validator(mode="after")
    def _an_absent_delta_says_why(self) -> ComparisonRow:
        if self.delta is None and not self.unavailable_because.strip():
            raise ValueError(
                f"{self.metric!r} has no delta and no reason; mark 12 requires a comparison that "
                "cannot be computed to say so rather than leave a column a reader fills in"
            )
        if self.delta is not None and self.previous is None:
            raise ValueError(
                f"{self.metric!r} publishes a delta with no previous value to subtract from"
            )
        return self


class SystemHealth(BaseModel):
    """The System Health workspace. Every figure read from a manifest, none derived here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generated: str
    commit_sha: str
    protocol_version: str

    injection: tuple[HealthRow, ...]
    vacuous_invariants: tuple[VacuousInvariant, ...]
    parser_corpus: tuple[HealthRow, ...]
    provenance: tuple[HealthRow, ...]
    limits: tuple[HealthRow, ...]
    not_applicable: tuple[NotApplicable, ...]

    expectation_ablation: ExpectationAblation
    retrieval_ablation: tuple[HealthRow, ...]
    retrieval_note: str
    calibration_note: str
    latency: tuple[HealthRow, ...]

    comparison: tuple[ComparisonRow, ...]
    comparison_note: str

    experiments: tuple[str, ...]
    """Ids and entry points that reproduce what this screen reports."""
