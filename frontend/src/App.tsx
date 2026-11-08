// The shell: header, navigation, and which workspace is showing.
//
// Three workspaces, from the console design's decision 1, with no numeric prefixes. Investigation
// detail is not a navigation item; it is a drill-down from the queue with a breadcrumb, because an
// investigation belongs to a well and a period rather than to a menu.

import { useEffect, useState } from "react";

import { fetchHeader, fetchHealth } from "./api";
import { Detail } from "./Detail";
import { Health } from "./Health";
import { Queue } from "./Queue";
import type { Header as HeaderPayload, SystemHealth } from "./types";

type Workspace = "production" | "drilling" | "system";

export function App(): JSX.Element {
  const [header, setHeader] = useState<HeaderPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("production");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    fetchHeader().then(setHeader, (reason: Error) => setError(reason.message));
  }, []);

  return (
    <>
      {header ? <Header header={header} /> : null}
      <nav>
        <button
          aria-current={workspace === "production"}
          onClick={() => {
            setWorkspace("production");
            setOpen(null);
          }}
        >
          Production
        </button>
        <button aria-current={workspace === "drilling"} onClick={() => setWorkspace("drilling")}>
          Drilling &amp; NPT
        </button>
        <button aria-current={workspace === "system"} onClick={() => setWorkspace("system")}>
          System Health
        </button>
      </nav>
      <main>
        {error ? <p className="error">The API is not reachable: {error}</p> : null}
        {workspace === "production" ? (
          open ? (
            <Detail investigationId={open} onBack={() => setOpen(null)} />
          ) : (
            <Queue onOpen={setOpen} />
          )
        ) : null}
        {workspace === "drilling" ? <Planned name="Drilling & NPT" /> : null}
        {workspace === "system" ? <HealthWorkspace /> : null}
      </main>
    </>
  );
}

function Header({ header }: { header: HeaderPayload }): JSX.Element {
  return (
    <>
      <div className="header">
        <span className="field">{header.field}</span>
        <span className="mode">{header.mode}</span>
        <span className="state">
          data through <b>{header.data_through}</b>
        </span>
        <span className="state">{header.production_availability}</span>
        <span className="state">{header.report_index_availability}</span>
        <span className="state" title={header.pressure_coverage}>
          pressure coverage <b>partial</b>
        </span>
        <span className="posture">{header.posture}</span>
      </div>
      {/* A popover, not a bar. The console design's decision 2 moves AI-engineering details out of
          the operator's main workflow: commit hashes, version strings and a label set's provenance
          are for the engineer, and this rendered them across the top of every screen. A pass
          through the running console found `provenance=machine_assisted` sitting there, which is
          the vocabulary decision 5 keeps off an operator screen. Collapsed by default, one click
          away, and nothing removed. */}
      <details className="build-info">
        <summary>Build info</summary>
        <div className="build-info-body">
          {Object.entries(header.build_info).map(([key, value]) => (
            <span key={key}>
              <b>{key}</b> {value}
            </span>
          ))}
        </div>
      </details>
    </>
  );
}

// The System Health workspace fetches on mount like every other screen. No cache: section 21.1,
// and a cached health figure is one that still carries the source that vouched for it when it was
// fresh.
function HealthWorkspace(): JSX.Element {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((reason: Error) => setFailed(reason.message));
  }, []);

  if (failed) {
    // Said plainly rather than rendered as an empty screen. The harnesses that write this
    // workspace's manifests are not run by the console, so the likely cause is that they have not
    // been run, and an empty health tab would look like a clean bill of health.
    return (
      <div className="planned-page">
        <h1>System Health</h1>
        <p className="error">
          Not available: {failed}. This screen reads <code>security_run.json</code> and{" "}
          <code>ablation_run.json</code>; run <code>scripts/run_security_checks.py</code> and{" "}
          <code>scripts/run_ablations.py</code> to produce them. Nothing is shown without them,
          because an empty health screen reads as a passing one.
        </p>
      </div>
    );
  }
  if (!health) return <p>Loading…</p>;
  return <Health health={health} />;
}

// A planned workspace gets a page saying what it will hold, rather than a dead tab. Decision 1:
// the structure is visible without the features being built, so a reader can see where this goes.
function Planned({ name }: { name: string }): JSX.Element {
  return (
    <div className="planned-page">
      <h1>{name}</h1>
      <p>
        Planned, and deliberately not stubbed with placeholder figures. The backend for this
        workspace exists: the post-mortem harness publishes recorded time in three categories, the
        lessons register and the correction store, and the evaluation harness publishes every gate
        and every figure the System Health screens would show.
      </p>
      <p>
        What is not built is this rendering. Protocol section 21.8 gates Phase 6 on the Production
        workspace and the three curated cases, and a screen filled with illustrative numbers to look
        complete is the one thing section 21.2 forbids outright.
      </p>
      <p>
        Until then the figures are in <code>docs/postmortem_results.md</code> and{" "}
        <code>docs/evaluation_results.md</code>, each one carrying its denominator.
      </p>
    </div>
  );
}
