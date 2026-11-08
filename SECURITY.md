# Security

This is a portfolio research project over a public dataset. It holds no personal data, no
credentials, and no proprietary material, and it is not deployed anywhere that handles either.

## Reporting a vulnerability

Open a GitHub issue. If the finding is one where a public issue is itself the problem, open an
issue saying only that you have something to report and asking for a contact route.

There is no bounty and no service-level commitment on response time.

## What this system is, for the purpose of judging a finding

**Nothing here is in a control loop.** There is no actuation path: no write to the event store, no
write to the correction store, no mutation of a finding, and no route that controls anything
physical. The one write the API has appends a review record. A finding is a piece of text a human
reads and judges.

**No module calls a language model.** Extraction is rule-based, the investigation controller is a
fixed sequence of deterministic stages, and the console renders what the harnesses published. This
changes which classes of finding apply: there is no prompt to inject into, and there is also no
model-shaped mitigation to rely on.

**The read-only posture reduces the operational risk surface and preserves human decision
authority. It is not a formal offshore safety case**, which is a far broader exercise involving
hazard identification, risk assessment, safety-critical elements and a regulator. A gate over the
repository's prose checks that nothing here claims otherwise.

## Trust boundaries

| Boundary | What crosses it | What guards it |
|---|---|---|
| Drilling-report XML | third-party documents | `ingest/safe_xml.py`: DTDs, entities, external references and XInclude refused, behind a size and extension allow-list |
| Archives | third-party bytes | `ingest/safe_archive.py`: path escape, symlink members, absolute and ratio-based decompression bombs, member counts, case and Unicode-normalisation collisions |
| Document text reaching a screen | untrusted prose | React escaping, plus a source gate forbidding every unescaped-markup sink in the frontend |
| HTTP API | request bodies and path parameters | typed Pydantic models, length-bounded operator strings, ids resolved against published rows before any path is built, per-client rate limits |
| Tool surface | query parameters | frozen, extra-forbidden models with a bounded date range per request |

## What is tested, and where

Protocol section 22 pre-registers the pass marks; `docs/security_results.md` reports what they
found. The marks run from:

- `scripts/run_security_checks.py` — the injection suite, the markup-sink gate, the overclaim
  gate, and the provenance and health checks
- `scripts/run_ablations.py` — the capability ablations
- `scripts/serve_injected_console.py` with `scripts/check_rendered_inert.js` — the rendered-DOM
  check, which is a browser experiment rather than a CI step
- `tests/test_security.py`, `tests/test_api_security.py`, `tests/test_provenance_failures.py`

Most of those tests break an invariant on purpose and require the suite to notice. A suite that
reported everything preserved on its first run, with no test that could fail, would be
indistinguishable from one that checks nothing.

## Known limitations

These are stated because a security document that lists only defences is a marketing document.

- **The rate limiter is per process** and keyed by the peer address. Two workers each allow the
  full rate. `X-Forwarded-For` is not trusted, so behind a proxy every client shares one bucket,
  which throttles everyone rather than nobody. Its window is fixed, so up to twice the limit can
  arrive across a window boundary.
- **The audit hook witnesses, it does not sandbox.** It records file opens, network connections,
  subprocess launches and dynamic compilation during a run. Nothing in it prevents any of them.
- **Three of the design brief's seven injection invariants are vacuous here** and are reported as
  vacuous rather than as preserved. They become live if a model-backed stage is ever added.
- **The rendered-DOM check is not automated.** The source gate that forbids markup sinks runs on
  every push; the empirical check that hostile text renders inert is run by hand against a served
  console.
- **Nested archives are not unpacked**, deliberately. A zip inside a zip is written as a file and
  left alone, because a recursive extractor is a new attack surface and nothing here needs one.

## Secrets

No credential is required to run anything in this repository. `.env.example` carries placeholders;
`.env` is gitignored, and CI checks on every push that no tracked path matches `_private/`,
`data/` or `.env`. The dataset is Equinor's public Volve release and is not committed.
