// The evidence drawer. The console design's decision 7.
//
// Every non-empty matrix cell opens one, and what it shows is the object behind the cell rather
// than a restatement of it. Three kinds, and the third is the one most systems do not have.
//
// A **fact**: the metric, both window values with their dates, the source table, the transformation
// and where to walk its lineage.
//
// A **document span**: the file, the date, the verbatim text and its offsets.
//
// An **absence**: the corpus searched, the filters, the queries issued and the count examined.
// Protocol section 21.3 stores absence as an object because a conclusion drawn from nothing looks
// identical to one drawn from something unless the nothing is recorded, and a blank cell is the
// most natural way to lose that distinction.
//
// Every drawer also states the deterministic rule that judged the cell, so a reader can disagree
// with the rule rather than only with the verdict.

import { Figure } from "./Sourced";
import type { MatrixCell } from "./types";

export function Drawer({
  cell,
  family,
  hypothesis,
  onClose,
}: {
  cell: MatrixCell;
  family: string;
  hypothesis: string;
  onClose: () => void;
}): JSX.Element {
  return (
    <aside className="drawer" aria-label="Evidence">
      <button className="close" onClick={onClose} aria-label="Close">
        ×
      </button>
      <h3>
        {hypothesis} · {family}
      </h3>
      <p style={{ fontSize: 13, marginTop: 6 }}>
        <strong>{cell.label}</strong>
      </p>
      <p style={{ fontSize: 12, color: "var(--steel-600)", lineHeight: 1.5 }}>
        <strong>The rule that judged this cell.</strong> {cell.rule}
      </p>

      {cell.fact ? (
        <>
          <h3 style={{ marginTop: 16 }}>Fact</h3>
          <dl>
            <dt>Fact id</dt>
            <dd>{cell.fact.fact_id}</dd>
            <dt>Metric</dt>
            <dd>{cell.fact.metric}</dd>
            <dt>Reference window</dt>
            <dd>{cell.fact.baseline_window}</dd>
            <dt>Value there</dt>
            <dd>
              <Figure figure={cell.fact.baseline_value} />
            </dd>
            <dt>Episode window</dt>
            <dd>{cell.fact.episode_window}</dd>
            <dt>Value there</dt>
            <dd>
              <Figure figure={cell.fact.episode_value} />
            </dd>
            <dt>Source table</dt>
            <dd>{cell.fact.source_table}</dd>
            <dt>Transformation</dt>
            <dd>{cell.fact.transformation}</dd>
            <dt>Lineage</dt>
            <dd>{cell.fact.derived_facts.join(", ") || "walk the facts artifact"}</dd>
          </dl>
        </>
      ) : null}

      {cell.document ? (
        <>
          <h3 style={{ marginTop: 16 }}>Document evidence</h3>
          <blockquote>{cell.document.span}</blockquote>
          <dl>
            <dt>Evidence id</dt>
            <dd>{cell.document.evidence_id}</dd>
            <dt>Source type</dt>
            <dd>{cell.document.source_type}</dd>
            <dt>Document</dt>
            <dd>{cell.document.document}</dd>
            <dt>Report date</dt>
            <dd>{cell.document.report_date}</dd>
            <dt>Span length</dt>
            <dd>
              <Figure figure={cell.document.end_offset} />
            </dd>
            <dt>Corpus checksum</dt>
            <dd>{cell.document.document_hash}</dd>
          </dl>
        </>
      ) : null}

      {cell.absence ? (
        <>
          <h3 style={{ marginTop: 16 }}>Recorded absence</h3>
          <p style={{ fontSize: 12.5, lineHeight: 1.5 }}>
            Retrieval ran and returned nothing. This is a recorded search with its own id, not an
            empty cell, and it lowers confidence rather than leaving it alone.
          </p>
          <dl>
            <dt>Absence id</dt>
            <dd>{cell.absence.absence_id}</dd>
            <dt>Corpus</dt>
            <dd>{cell.absence.corpus}</dd>
            <dt>Filters</dt>
            <dd>{cell.absence.filters.join("; ")}</dd>
            <dt>Queries</dt>
            <dd>{cell.absence.queries.join("; ")}</dd>
            <dt>Documents examined</dt>
            <dd>
              <Figure figure={cell.absence.documents_examined} />
            </dd>
            <dt>Outcome</dt>
            <dd>{cell.absence.outcome.replace(/_/g, " ")}</dd>
          </dl>
        </>
      ) : null}
    </aside>
  );
}
