// The System Health workspace. Protocol section 22, marks 11 and 12.
//
// Everything here is read from a payload the harnesses wrote. Section 21.1 holds on this screen as
// on every other: it renders, and it does not compute. That includes the comparison table, where a
// delta is published by the harness that owns both arms or it does not appear at all.
//
// Two display decisions carry the two findings this phase cares most about.
//
// The vacuous invariants are a separate block with their reasons, never a row in the counts. Three
// of the design brief's seven injection invariants have nothing to hold against in a system that
// calls no model, and a screen that listed them beside the ones that were tested would undo in the
// display what the report structure exists to prevent.
//
// The comparison table prints a reason where a delta would go. An empty delta column reads as no
// change, and a 0.00 against a baseline that does not exist is a figure from nowhere.

import type { ComparisonRow, HealthRow, SystemHealth } from "./types";
import { Figure } from "./Sourced";

function Rows({ rows }: { rows: HealthRow[] }): JSX.Element {
  return (
    <table className="health-rows">
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <td>{row.label}</td>
            <td className="figure">
              <Figure figure={row.value} />
            </td>
            <td className="note">{row.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Comparison({ rows, note }: { rows: ComparisonRow[]; note: string }): JSX.Element {
  return (
    <div className="panel">
      <header>
        <h2>Version comparison</h2>
        <span style={{ fontSize: 12, color: "var(--steel-600)" }}>{note}</span>
      </header>
      <table className="health-rows">
        <thead>
          <tr>
            <th>Metric</th>
            <th>This version</th>
            <th>Previous</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.metric}>
              <td>{row.metric}</td>
              <td className="figure">
                <Figure figure={row.current} />
              </td>
              <td className="figure">
                {row.previous ? <Figure figure={row.previous} /> : <span className="absent">no previous version</span>}
              </td>
              <td className="note">
                {row.delta ? (
                  <Figure figure={row.delta} />
                ) : (
                  <span className="absent">{row.unavailable_because}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Health({ health }: { health: SystemHealth }): JSX.Element {
  const ablation = health.expectation_ablation;
  return (
    <div className="health">
      <div className="panel">
        <header>
          <h2>Injection invariants</h2>
          <span style={{ fontSize: 12, color: "var(--steel-600)" }}>
            protocol {health.protocol_version} · {health.generated}
          </span>
        </header>
        <Rows rows={health.injection} />
        <div className="vacuous">
          <h3>Declared vacuous, and not counted as preserved</h3>
          <p>
            Three of the design brief&rsquo;s seven injection invariants presume a language model
            reading document text. No module here calls one, so they have nothing to hold against.
            They are reported with their reasons rather than counted as invariants the system kept.
          </p>
          <dl>
            {health.vacuous_invariants.map((invariant) => (
              <div key={invariant.key}>
                <dt>{invariant.wording}</dt>
                <dd>{invariant.reason}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>Parsers, archives and the rendering layer</h2>
        </header>
        <Rows rows={health.parser_corpus} />
      </div>

      <div className="panel">
        <header>
          <h2>Provenance failures</h2>
        </header>
        <Rows rows={health.provenance} />
      </div>

      <div className="panel">
        <header>
          <h2>Expectation ablation</h2>
          <span style={{ fontSize: 12, color: "var(--steel-600)" }}>
            how much work each expectation model creates, beside how accurate it is
          </span>
        </header>
        <table className="health-rows">
          <thead>
            <tr>
              <th>Model</th>
              <th>Episodes opened</th>
              <th>WAPE</th>
            </tr>
          </thead>
          <tbody>
            {ablation.rows.map((row) => (
              <tr key={row.model}>
                <td>{row.model}</td>
                <td className="figure">{row.episodes_opened}</td>
                <td className="figure">{row.wape === null ? "not reported" : row.wape.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note" title={ablation.source}>
          {ablation.row_count.value} models compared, from {ablation.source}
        </p>
      </div>

      <div className="panel">
        <header>
          <h2>Retrieval ablation</h2>
        </header>
        <Rows rows={health.retrieval_ablation} />
        <p className="note">{health.retrieval_note}</p>
      </div>

      <div className="panel">
        <header>
          <h2>Calibration</h2>
        </header>
        <p className="note">{health.calibration_note}</p>
      </div>

      <div className="panel">
        <header>
          <h2>Latency and cost</h2>
        </header>
        <Rows rows={health.latency} />
        <div className="vacuous">
          <h3>Not applicable here, and why</h3>
          <dl>
            {health.not_applicable.map((item) => (
              <div key={item.key}>
                <dt>{item.key.replace(/_/g, " ")}</dt>
                <dd>{item.reason}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>Request bounds</h2>
        </header>
        <Rows rows={health.limits} />
      </div>

      <Comparison rows={health.comparison} note={health.comparison_note} />

      <div className="panel">
        <header>
          <h2>What reproduces this</h2>
        </header>
        <ul className="experiments">
          {health.experiments.map((entry) => (
            <li key={entry}>
              <code>{entry}</code>
            </li>
          ))}
        </ul>
        <p className="note">commit {health.commit_sha}</p>
      </div>
    </div>
  );
}
