// The shell: header, navigation, and which workspace is showing.
//
// Three workspaces, from the console design's decision 1, with no numeric prefixes. Investigation
// detail is not a navigation item; it is a drill-down from the queue with a breadcrumb, because an
// investigation belongs to a well and a period rather than to a menu.

import { useEffect, useState } from "react";

import { fetchHeader } from "./api";
import { Detail } from "./Detail";
import { Queue } from "./Queue";
import type { Header as HeaderPayload } from "./types";

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
        {workspace === "drilling" ? <Planned name="Drilling &amp; NPT" /> : null}
        {workspace === "system" ? <Planned name="System Health" /> : null}
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
      <div className="build-info">
        {Object.entries(header.build_info).map(([key, value]) => (
          <span key={key}>
            <b>{key}</b> {value}
          </span>
        ))}
      </div>
    </>
  );
}

// A planned workspace gets a page saying what it will hold, rather than a dead tab. Decision 1:
// the structure is visible without the features being built, so a reader can see where this goes.
function Planned({ name }: { name: string }): JSX.Element {
  return (
    <div className="planned-page">
      <h1 dangerouslySetInnerHTML={{ __html: name }} />
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
