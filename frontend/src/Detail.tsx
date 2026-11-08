// The investigation detail screen. The console design's decision 4, and the signature of the whole
// product.
//
// The order is the order an operator reads in, and it is not a chat log. Chart, then the hypothesis
// and evidence matrix, then the assessment, then what evidence is available and what is missing,
// then human review, then audit and provenance collapsed by default.
//
// An operator must be able to answer eight questions without leaving this page: what is the
// conclusion, what supports it, what contradicts it, what data is missing, where each number came
// from, how expected production was calculated, what would change the conclusion, and whether a
// human has reviewed it. Every section below exists to answer one of them.

import { useEffect, useState } from "react";

import { fetchDetail, fetchReview, postReview } from "./api";
import { Chart } from "./Chart";
import { Drawer } from "./Drawer";
import { Figure } from "./Sourced";
import type { InvestigationDetail, MatrixCell, ReviewHistory } from "./types";

interface OpenCell {
  cell: MatrixCell;
  family: string;
  hypothesis: string;
}

export function Detail({
  investigationId,
  onBack,
}: {
  investigationId: string;
  onBack: () => void;
}): JSX.Element {
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [review, setReview] = useState<ReviewHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<OpenCell | null>(null);

  useEffect(() => {
    setDetail(null);
    fetchDetail(investigationId).then(setDetail, (reason: Error) => setError(reason.message));
    fetchReview(investigationId).then(setReview, () => setReview(null));
  }, [investigationId]);

  if (error) return <p className="error">{error}</p>;
  if (!detail) return <p className="loading">Reading the investigation artifacts.</p>;

  return (
    <>
      <div className="breadcrumb">
        <button onClick={onBack}>Production</button> → <button onClick={onBack}>Investigation
        Queue</button> → {detail.well} → {detail.investigation_id}
      </div>

      <div className="panel">
        <header>
          <h1>
            {detail.well} · {detail.period}
          </h1>
        </header>
        <div className="body verdict-card">
          <div>
            <div className="headline">{detail.assessment_label}</div>
            <div className="level">Causal level reached: {detail.causal_level_label}</div>
          </div>
          <div style={{ flex: "1 1 420px", fontSize: 13, lineHeight: 1.55 }}>
            {detail.narrative}
          </div>
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>Production against expectation</h2>
          <span style={{ fontSize: 12, color: "var(--steel-600)" }}>
            {detail.chart.episode_window}, with{" "}
            <Figure figure={detail.chart.row_count} /> days shown
          </span>
        </header>
        <div className="body">
          <Chart chart={detail.chart} />
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>How the expectation was built</h2>
        </header>
        <div className="body">
          <dl
            style={{
              display: "grid",
              gridTemplateColumns: "210px 1fr",
              gap: "5px 14px",
              fontSize: 12.5,
              margin: 0,
            }}
          >
            <dt style={{ color: "var(--steel-600)" }}>Model</dt>
            <dd style={{ margin: 0 }} className="mono">
              {detail.expectation.model_name} ({detail.expectation.model_version})
            </dd>
            <dt style={{ color: "var(--steel-600)" }}>Reference window</dt>
            <dd style={{ margin: 0 }}>{detail.expectation.reference_window}</dd>
            <dt style={{ color: "var(--steel-600)" }}>Operating regime</dt>
            <dd style={{ margin: 0 }}>{detail.expectation.regime}</dd>
            <dt style={{ color: "var(--steel-600)" }}>Backtest WAPE, 7 days</dt>
            <dd style={{ margin: 0 }}>
              <Figure figure={detail.expectation.backtest_wape} />
            </dd>
            <dt style={{ color: "var(--steel-600)" }}>Lower-tail rate</dt>
            <dd style={{ margin: 0 }}>
              <Figure figure={detail.expectation.interval_coverage} />{" "}
              <span style={{ color: "var(--contradicts)" }}>
                against a permitted 0.05 to 0.20
              </span>
            </dd>
          </dl>
          <p style={{ fontSize: 12, color: "var(--steel-600)", marginTop: 11, lineHeight: 1.55 }}>
            {detail.expectation.note}
          </p>
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>Hypotheses and evidence</h2>
          <span style={{ fontSize: 12, color: "var(--steel-600)" }}>
            Every judged cell opens the object behind it
          </span>
        </header>
        <table className="matrix">
          <thead>
            <tr>
              <th>Hypothesis</th>
              {detail.evidence_families.map((family) => (
                <th key={family} style={{ textAlign: "center" }}>
                  {family}
                </th>
              ))}
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {detail.hypotheses.map((hypothesis) => (
              <tr key={hypothesis.hypothesis_id}>
                <td>{hypothesis.label}</td>
                {detail.evidence_families.map((family) => {
                  const cell = hypothesis.cells[family];
                  if (!cell) return <td key={family} className="cell not_applicable" />;
                  const clickable = cell.verdict !== "not_applicable";
                  return (
                    <td
                      key={family}
                      className={`cell ${cell.verdict}`}
                      title={cell.rule}
                      onClick={
                        clickable
                          ? () => setOpen({ cell, family, hypothesis: hypothesis.label })
                          : undefined
                      }
                    >
                      {cell.label}
                    </td>
                  );
                })}
                <td>{hypothesis.status_label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <header>
          <h2>Assessment</h2>
        </header>
        <div className="body" style={{ fontSize: 13, lineHeight: 1.6 }}>
          <p style={{ marginTop: 0 }}>
            <strong>What would change this conclusion.</strong>{" "}
            {detail.what_would_change_the_conclusion || "Not recorded for this finding."}
          </p>
          <p style={{ marginBottom: 0 }}>
            <strong>Recommended next check.</strong> {detail.recommended_next_check}
          </p>
        </div>
      </div>

      <div className="panel">
        <header>
          <h2>Evidence coverage</h2>
        </header>
        <div className="body coverage">
          <div className="available">
            <h3>Available</h3>
            <ul>
              {detail.coverage.available.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div className="missing">
            <h3>Missing or insufficient</h3>
            {detail.coverage.missing.length === 0 ? (
              <p style={{ fontSize: 12.5, color: "var(--steel-600)" }}>Nothing missing.</p>
            ) : (
              <ul>
                {detail.coverage.missing.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <Review
        investigationId={investigationId}
        actions={detail.review_actions}
        disclaimer={detail.review_disclaimer}
        review={review}
        onChange={setReview}
      />

      <details className="audit">
        <summary>Audit and provenance</summary>
        <div className="body">
          <dl
            style={{
              display: "grid",
              gridTemplateColumns: "210px 1fr",
              gap: "5px 14px",
              fontSize: 12,
              margin: 0,
            }}
          >
            {Object.entries(detail.provenance).map(([key, value]) => (
              <div key={key} style={{ display: "contents" }}>
                <dt style={{ color: "var(--steel-600)" }}>{key}</dt>
                <dd className="mono" style={{ margin: 0 }}>
                  {value}
                </dd>
              </div>
            ))}
            <dt style={{ color: "var(--steel-600)" }}>chart series</dt>
            <dd className="mono" style={{ margin: 0 }}>
              {detail.chart.source}
            </dd>
          </dl>
          <p style={{ fontSize: 12, color: "var(--steel-600)", marginTop: 12, lineHeight: 1.55 }}>
            The trace is a record of actions: which stage ran, what it looked at, what it cost. It is
            not a model's intermediate text, and no model was called to produce this finding.
          </p>
        </div>
      </details>

      {open ? (
        <Drawer
          cell={open.cell}
          family={open.family}
          hypothesis={open.hypothesis}
          onClose={() => setOpen(null)}
        />
      ) : null}
    </>
  );
}

// Human review. Decision 6: none of these is called "approve", and the panel says in words that a
// review records a judgement of the assessment and authorises nothing. A settled finding is
// immutable, so once it is confirmed or dismissed the buttons go away rather than failing on click.
function Review({
  investigationId,
  actions,
  disclaimer,
  review,
  onChange,
}: {
  investigationId: string;
  actions: Record<string, string>;
  disclaimer: string;
  review: ReviewHistory | null;
  onChange: (next: ReviewHistory) => void;
}): JSX.Element {
  const [actor, setActor] = useState("");
  const [note, setNote] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const settled = review?.state === "confirmed" || review?.state === "dismissed";

  const send = (action: string) => {
    setFailed(null);
    postReview(investigationId, action, actor, note || undefined).then(
      (next) => {
        onChange(next);
        setNote("");
      },
      (reason: Error) => setFailed(reason.message),
    );
  };

  return (
    <div className="panel">
      <header>
        <h2>Human review</h2>
        <span style={{ fontSize: 12, color: "var(--steel-600)" }}>
          state: {review?.state ?? "not reviewed"}
        </span>
      </header>
      <div className="body">
        {settled ? (
          <p style={{ fontSize: 13, margin: 0 }}>
            This finding is {review?.state}. A settled finding is immutable: a person who put their
            name to an assessment cannot be made to vouch for a different one. Record a new
            investigation run if the evidence has changed.
          </p>
        ) : (
          <>
            <div className="review">
              <label>
                <div style={{ fontSize: 11, color: "var(--steel-600)" }}>Reviewer</div>
                <input
                  value={actor}
                  onChange={(event) => setActor(event.target.value)}
                  placeholder="your name"
                  size={18}
                />
              </label>
              <label style={{ flex: "1 1 260px" }}>
                <div style={{ fontSize: 11, color: "var(--steel-600)" }}>
                  Note (required for a correction)
                </div>
                <input
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  style={{ width: "100%" }}
                />
              </label>
              <button disabled={!actor} onClick={() => send("confirm")}>
                {actions["confirm"]}
              </button>
              <button className="secondary" disabled={!actor} onClick={() => send("dismiss")}>
                {actions["dismiss"]}
              </button>
              <button
                className="secondary"
                disabled={!actor}
                onClick={() => send("request_more_evidence")}
              >
                {actions["request_more_evidence"]}
              </button>
              <button
                className="secondary"
                disabled={!actor || !note}
                onClick={() => send("add_correction")}
              >
                {actions["add_correction"]}
              </button>
            </div>
            {failed ? <p className="error">{failed}</p> : null}
          </>
        )}
        <p className="disclaimer">{disclaimer}</p>
        {review && review.records.length > 0 ? (
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th className="num">Revision</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {review.records.map((record) => (
                <tr key={`${record.recorded_at}-${record.action}`}>
                  <td className="mono">{record.recorded_at}</td>
                  <td>{record.actor}</td>
                  <td>{actions[record.action] ?? record.action}</td>
                  <td className="num mono">{record.revision}</td>
                  <td>{record.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </div>
  );
}
