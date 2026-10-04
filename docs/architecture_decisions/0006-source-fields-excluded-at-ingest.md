# ADR 0006: identifying fields in the source are dropped at ingest and never published

Date: 2026-10-04
Status: accepted

## Context

The realtime drilling data in this dataset carries per-record audit metadata from the system
that produced it. Every message sampled contained fields recording a named account that owned
or last changed the record, and the internal IP addresses those changes came from.

This project publishes quoted evidence spans into a public repository and a public interface.
Nothing in the original design anticipated that the source documents would contain identifying
information about individual people, so nothing in it prevented such a field from being carried
into a stored Fact, a quoted span, or a published Finding.

## Decision

Audit and identity metadata is dropped at ingest, before anything is stored. It is not
retained in a canonical record, not indexed for retrieval, not available to a tool, and not
quotable as evidence. The parser removes the fields rather than filtering them later, so there
is no path by which a downstream component can reach them.

This applies to account names, user identifiers, email addresses and network addresses,
whatever element they appear in and whichever source they come from.

## Consequences

Nothing of analytical value is lost. These fields describe who synchronised a record and from
which machine, which is irrelevant to every question this system asks.

Dropping at ingest rather than at publication is deliberate. A redaction step late in the
pipeline has to be correct every time on every path; a field that was never stored cannot leak
through a path nobody thought about.

The ingest layer needs a test proving these fields do not survive, and that test belongs in the
cheap suite that runs on every change, because this is the kind of guarantee that quietly
regresses when a parser is extended.
