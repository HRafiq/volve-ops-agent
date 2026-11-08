// The shapes the API serves, mirroring `volve_ops.console.payloads`.
//
// Every figure arrives as a `Sourced`: a value with the manifest key, fact id, event id, artifact
// or pre-registered rule it came from. That is protocol section 21.6 mark 1, and the reason it
// reaches the type system here is that a component cannot then render a number without having its
// source in hand to show beside it.

export type SourceKind = string;

export interface Sourced {
  value: number | boolean | null;
  source: SourceKind;
  unit: string | null;
  denominator: string | null;
}

// An estimated currency figure, inseparable from its assumption. `amount` is null on every run so
// far, because a rig day rate and an oil price are commercial figures this project has no access to.
export interface Money {
  amount: Sourced | null;
  assumption: string | null;
  reason: string | null;
}

export interface Kpi {
  label: string;
  figure: Sourced | null;
  money: Money | null;
  note: string | null;
}

export interface QueueRow {
  investigation_id: string;
  well: string;
  period: string;
  actual_rate: Sourced;
  expected_rate: Sourced;
  cumulative_shortfall: Sourced;
  deferred_volume: Sourced;
  episode_days: Sourced;
  assessment: string;
  assessment_label: string;
  causal_level_label: string;
  evidence_strength: string;
  review_state: string;
  review_state_label: string;
  data_quality: string;
  priority: "HIGH" | "MEDIUM" | "LOW";
  priority_score: Sourced;
  priority_explanation: string;
}

export interface PriorityRule {
  statement: string[];
  term_counts: Record<string, Sourced>;
  caveat: string;
}

export interface Queue {
  kpis: Kpi[];
  rows: QueueRow[];
  rule: PriorityRule;
  pinned: string[];
}

export interface Header {
  field: string;
  mode: string;
  data_through: string;
  production_availability: string;
  report_index_availability: string;
  pressure_coverage: string;
  posture: string;
  build_info: Record<string, string>;
}

export interface SeriesRow {
  date: string;
  day_class: string;
  actual: number | null;
  expected: number | null;
  lower: number | null;
  upper: number | null;
  below_band: boolean;
  on_stream_hours: number | null;
  choke_size: number | null;
  downhole_pressure_bar: number | null;
  wellhead_pressure_bar: number | null;
  water_cut: number | null;
}

// A table of records, vouched for by one source plus a row count the gate checks. Amendment 10's
// declared exemption to mark 1: 109 days of ten channels is 1,090 numbers from one artifact, and a
// source object around each would repeat one answer a thousand times.
export interface ChartSeries {
  source: string;
  rows: SeriesRow[];
  row_count: Sourced;
  episode_window: string;
  governing_window: string;
}

// One fact from the provenance ledger, carrying the value the ledger records.
//
// Its own value, which is the point. The drawer used to attach ledger ids to figures taken from
// elsewhere: `fact_000002` records a reference rate of 3,052.735 Sm3/d and the drawer published
// 4,351.41 under its id. 198 of 198 fact-sourced figures were mis-attributed, and every source
// resolved, so the gate passed on all of them.
export interface LedgerFact {
  fact_id: string;
  metric: string;
  value: Sourced;
  kind: string;
}

export interface FactEvidence {
  reference: string;
  metric: string;
  value: Sourced;
  baseline_value: Sourced;
  episode_value: Sourced;
  baseline_window: string;
  episode_window: string;
  source_table: string;
  transformation: string;
  ledger_facts: LedgerFact[];
}

export interface DocumentEvidence {
  evidence_id: string;
  source_type: string;
  document: string;
  report_date: string;
  span: string;
  start_offset: Sourced;
  end_offset: Sourced;
  document_hash: string;
}

// A recorded search that found nothing, with its own id. Section 21.3: a conclusion drawn from
// nothing looks identical to one drawn from something unless the nothing is recorded.
export interface Absence {
  absence_id: string;
  corpus: string;
  filters: string[];
  queries: string[];
  documents_examined: Sourced;
  outcome: "none_found" | "reason_not_documented";
}

export type CellVerdict = "supports" | "contradicts" | "neutral" | "absent" | "not_applicable";

export interface MatrixCell {
  verdict: CellVerdict;
  label: string;
  rule: string;
  fact: FactEvidence | null;
  document: DocumentEvidence | null;
  absence: Absence | null;
}

export interface Hypothesis {
  hypothesis_id: string;
  label: string;
  status: string;
  status_label: string;
  cells: Record<string, MatrixCell>;
}

export interface EvidenceCoverage {
  available: string[];
  missing: string[];
}

export interface ExpectationPanel {
  model_name: string;
  model_version: string;
  reference_window: string;
  regime: string;
  backtest_wape: Sourced;
  lower_tail_rate: Sourced;
  note: string;
}

export interface InvestigationDetail {
  investigation_id: string;
  well: string;
  period: string;
  assessment_label: string;
  causal_level_label: string;
  narrative: string;
  what_would_change_the_conclusion: string;
  recommended_next_check: string;
  chart: ChartSeries;
  expectation: ExpectationPanel;
  hypotheses: Hypothesis[];
  evidence_families: string[];
  coverage: EvidenceCoverage;
  review_disclaimer: string;
  review_actions: Record<string, string>;
  provenance: Record<string, string>;
}

export interface ReviewRecord {
  investigation_id: string;
  action: string;
  actor: string;
  recorded_at: string;
  note: string | null;
  revision: number;
  investigator_version: string;
  protocol_version: string;
}

export interface ReviewHistory {
  investigation_id: string;
  state: string;
  state_label: string;
  records: ReviewRecord[];
  actions: Record<string, string>;
  disclaimer: string;
}

// --- the System Health workspace, protocol section 22 ---------------------------------------

export interface HealthRow {
  label: string;
  value: Sourced;
  note: string;
}

export interface VacuousInvariant {
  key: string;
  wording: string;
  reason: string;
}

export interface NotApplicable {
  key: string;
  reason: string;
}

export interface ComparisonRow {
  metric: string;
  current: Sourced;
  previous: Sourced | null;
  delta: Sourced | null;
  unavailable_because: string;
}

export interface ExpectationAblationRow {
  model: string;
  episodes_opened: number;
  wape: number | null;
}

export interface ExpectationAblation {
  source: string;
  row_count: Sourced;
  rows: ExpectationAblationRow[];
}

export interface SystemHealth {
  generated: string;
  commit_sha: string;
  protocol_version: string;
  injection: HealthRow[];
  vacuous_invariants: VacuousInvariant[];
  parser_corpus: HealthRow[];
  provenance: HealthRow[];
  limits: HealthRow[];
  not_applicable: NotApplicable[];
  expectation_ablation: ExpectationAblation;
  retrieval_ablation: HealthRow[];
  retrieval_note: string;
  calibration_note: string;
  latency: HealthRow[];
  comparison: ComparisonRow[];
  comparison_note: string;
  experiments: string[];
}
