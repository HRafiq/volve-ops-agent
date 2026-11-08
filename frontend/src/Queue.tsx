// The investigation queue and its KPI strip. The console design's decisions 3 and 9.
//
// Two things the design is specific about and this implements literally.
//
// The priority rule is printed under the table with each row's own score, and with the count of
// episodes each term fired on. ADR 0009 is why the counts are there rather than only the rubric: a
// four-line rule of which one line fires on nothing reads as more considered than it is, and the
// only honest fix is to publish how often each line fires.
//
// Pinned investigations sit below the queue rather than above it. They exist so a visitor can
// understand the system in five minutes, and the queue is what an operator actually works from.

import { useEffect, useState } from "react";

import { fetchQueue } from "./api";
import { Figure, MoneyFigure } from "./Sourced";
import type { Queue as QueuePayload, QueueRow } from "./types";

const ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

export function Queue({ onOpen }: { onOpen: (id: string) => void }): JSX.Element {
  const [queue, setQueue] = useState<QueuePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchQueue().then(setQueue, (reason: Error) => setError(reason.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!queue) return <p className="loading">Reading the run manifests.</p>;

  // Sorting is selection, not computation: the scores come from the payload. Default is priority
  // then shortfall, which decision 9 fixes.
  const rows = [...queue.rows].sort((a, b) => {
    const byPriority = (ORDER[a.priority] ?? 9) - (ORDER[b.priority] ?? 9);
    if (byPriority !== 0) return byPriority;
    return Number(b.cumulative_shortfall.value ?? 0) - Number(a.cumulative_shortfall.value ?? 0);
  });
  const pinned = rows.filter((row) => queue.pinned.includes(row.investigation_id));

  return (
    <>
      <div className="kpis">
        {queue.kpis.map((kpi) => (
          <div className="kpi" key={kpi.label}>
            <div className="label">{kpi.label}</div>
            {kpi.money ? (
              <MoneyFigure money={kpi.money} />
            ) : kpi.figure ? (
              <>
                <div className="value">
                  <Figure figure={kpi.figure} />
                </div>
                <div className="denominator">{kpi.figure.denominator}</div>
              </>
            ) : null}
            {kpi.note ? <div className="note">{kpi.note}</div> : null}
          </div>
        ))}
      </div>

      <div className="panel">
        <header>
          <h2>Investigation queue</h2>
          <span className="state" style={{ color: "var(--steel-600)", fontSize: 12 }}>
            {rows.length} episodes, sorted by priority then cumulative shortfall
          </span>
        </header>
        <Table rows={rows} onOpen={onOpen} />
      </div>

      <div className="rule">
        <h3>How priority is decided</h3>
        <ol>
          {queue.rule.statement.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
        <div className="counts">
          {Object.entries(queue.rule.term_counts).map(([term, count]) => (
            <span key={term}>
              <Figure figure={count} /> &nbsp;{term}
            </span>
          ))}
        </div>
        <p className="caveat">{queue.rule.caveat}</p>
      </div>

      {pinned.length > 0 ? (
        <div className="panel" style={{ marginTop: 18 }}>
          <header>
            <h2>Pinned investigations</h2>
            <span style={{ color: "var(--steel-600)", fontSize: 12 }}>
              One supported case, one unresolved, one with no conclusion issued. A five-minute tour,
              not a work queue.
            </span>
          </header>
          <Table rows={pinned} onOpen={onOpen} />
        </div>
      ) : null}
    </>
  );
}

function Table({
  rows,
  onOpen,
}: {
  rows: QueueRow[];
  onOpen: (id: string) => void;
}): JSX.Element {
  return (
    <table>
      <thead>
        <tr>
          <th>Well</th>
          <th>Period</th>
          <th className="num">Actual</th>
          <th className="num">Expected</th>
          <th className="num">Shortfall</th>
          <th className="num">Days</th>
          <th>Assessment</th>
          <th>Causal level</th>
          <th>Evidence strength</th>
          <th>Review</th>
          <th>Data quality</th>
          <th>Priority</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.investigation_id}
            className="clickable"
            onClick={() => onOpen(row.investigation_id)}
          >
            <td className="mono">{row.well}</td>
            <td className="mono">{row.period}</td>
            <td className="num">
              <Figure figure={row.actual_rate} />
            </td>
            <td className="num">
              <Figure figure={row.expected_rate} />
            </td>
            <td className="num">
              <Figure figure={row.cumulative_shortfall} />
            </td>
            <td className="num">
              <Figure figure={row.episode_days} />
            </td>
            <td>{row.assessment_label}</td>
            <td>{row.causal_level_label}</td>
            <td>{row.evidence_strength}</td>
            <td>{row.review_state_label}</td>
            <td>
              {row.data_quality === "Degraded" ? (
                <span className="pill degraded">Degraded</span>
              ) : (
                row.data_quality
              )}
            </td>
            <td title={row.priority_explanation}>
              <span className={`pill ${row.priority}`}>{row.priority}</span>{" "}
              <Figure figure={row.priority_score} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
