"""Protocol section 22: the injection suite, and the proof that it can fail.

This file exists because a suite that reports every invariant preserved on its first run is
indistinguishable from a suite that checks nothing, and five amendments to this project's
protocol correct pass marks that could not fail. So most of what follows breaks one invariant on
purpose and requires the suite to notice. A test that only asserts the clean run passes would be
the seventh instance of the defect.

Two findings from the suite's own development are pinned here as tests, because both were real
and both would silently return:

- a report holding nothing but the three vacuous declarations once reported `passed`, since it
  had no violations and no unreached fixtures. A suite that ran nothing passed.
- the markup invariant once yielded `held` unconditionally at the investigation level, inflating
  the preserved count by one per payload while examining nothing.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from volve_ops.extraction.npt import extract_from_report
from volve_ops.investigation.schemas import CausalLevel, Finding, Verdict
from volve_ops.investigation.trace import Stage
from volve_ops.security import suite
from volve_ops.security.attacks import (
    ARCHIVE_ATTACKS,
    PARSES_CORRECTLY,
    XML_ATTACKS,
    Attack,
)
from volve_ops.security.invariants import (
    ALL_INVARIANTS,
    LIVE_INVARIANTS,
    VACUOUS_INVARIANTS,
    Invariant,
    Outcome,
    Report,
    Result,
    Status,
    unexercised_live_invariants,
    vacuous_declarations,
)
from volve_ops.security.observation import observing
from volve_ops.security.payloads import (
    ALL_PAYLOADS,
    MARKER_PREFIX,
    InjectionClass,
    Payload,
    by_marker,
    payloads_of,
)

MARKERS = by_marker()


@pytest.fixture(scope="module")
def control() -> suite.InvestigationArm:
    arm = suite.InvestigationArm(suite.BENIGN_COMMENT)
    suite.check_control_arm_is_valid(arm)
    return arm


class _Arm:
    """A real arm with one thing changed, for breaking one invariant at a time.

    Satisfies `suite.Arm`, which is the protocol the invariant checks consume. Substituting here
    is the only way to break one invariant without breaking the controller, which is what makes
    the checks in this file proofs that the suite can fail rather than restatements of it.
    """

    def __init__(
        self,
        real: suite.InvestigationArm,
        *,
        finding: Finding | None = None,
        queries: tuple[str, ...] | None = None,
        stages: tuple[Stage, ...] | None = None,
    ) -> None:
        self._real = real
        self._queries = queries
        self._stages = stages
        self.text = real.text
        self.ledger = real.ledger
        self._finding = finding if finding is not None else real.finding

    @property
    def finding(self) -> Finding:
        return self._finding

    @property
    def trace(self) -> Any:
        if self._stages is None:
            return self._real.trace
        return SimpleNamespace(steps=self._real.trace.steps, stages=self._stages)

    def queries(self) -> tuple[str, ...]:
        return self._real.queries() if self._queries is None else self._queries

    def published(self) -> str:
        return self._real.published()


class TestTheCorpusIsWellFormed:
    """A fixture defect is invisible in a report that only counts outcomes."""

    def test_every_payload_contains_its_own_marker(self) -> None:
        # Enforced by a model validator, so this asserts the validator is wired rather than
        # re-deriving the rule. A payload whose marker is absent could never be located
        # downstream and would report as not reached forever.
        for payload in ALL_PAYLOADS:
            assert payload.marker in payload.text

    def test_markers_are_unique(self) -> None:
        markers = [p.marker for p in ALL_PAYLOADS]
        assert len(set(markers)) == len(markers)

    def test_a_payload_without_its_marker_is_refused(self) -> None:
        with pytest.raises(ValueError, match="does not contain its own marker"):
            Payload(
                name="bad",
                injection_class=InjectionClass.MARKUP,
                marker=f"{MARKER_PREFIX}999",
                text="no marker here",
                attempts="nothing",
            )

    def test_a_marker_carrying_the_payloads_own_trick_is_refused(self) -> None:
        # A marker with a zero-width character in it could not be searched for, so the fixture
        # would report as not reached while in fact arriving: the same error in reverse.
        with pytest.raises(ValueError, match="plain ASCII"):
            Payload(
                name="bad",
                injection_class=InjectionClass.UNICODE_AND_ENCODING,
                marker=f"{MARKER_PREFIX}​1",
                text=f"{MARKER_PREFIX}​1",
                attempts="nothing",
            )

    def test_all_six_classes_are_populated(self) -> None:
        for injection_class in InjectionClass:
            assert payloads_of(injection_class), f"class {injection_class} has no payload"


class TestVacuityIsStructural:
    """Section 22.4 mark 1: a vacuous invariant is never counted as one preserved."""

    def test_three_invariants_are_declared_vacuous_with_reasons(self) -> None:
        assert len(VACUOUS_INVARIANTS) == 3
        for invariant in VACUOUS_INVARIANTS:
            assert len(invariant.reason) > 50

    def test_a_vacuous_invariant_cannot_produce_a_held_result(self) -> None:
        held = Result(
            invariant=VACUOUS_INVARIANTS[0].key,
            payload="anything",
            outcome=Outcome.HELD,
            detail="d",
        )
        with pytest.raises(ValueError, match="forbids counting an invariant"):
            Report(results=(held,))

    def test_a_vacuous_declaration_without_a_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="requires the reason"):
            Invariant(key="k", brief_wording="w", status=Status.VACUOUS, reason="too short")

    def test_a_report_that_ran_nothing_does_not_pass(self) -> None:
        # The first version of Report.passed consulted only the violation and reachability
        # counts, so this report passed: zero violations, zero unreached, nothing tested.
        report = Report(results=vacuous_declarations())
        assert report.violated == 0
        assert report.finished is True
        assert report.passed is False
        assert len(report.unexercised) == len(LIVE_INVARIANTS)

    def test_the_replaced_invariant_says_what_it_stands_in_for(self) -> None:
        replacement = next(i for i in ALL_INVARIANTS if i.stands_in_for)
        assert replacement.stands_in_for == "tool_initiation_as_written"
        assert replacement.status is Status.LIVE


class TestReachabilityCanFail:
    """Section 22.2: a fixture whose payload never arrived has not tested anything."""

    def test_a_payload_in_a_field_nothing_reads_is_not_reached(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ301"]
        xml = suite.report_xml("ordinary comment").replace(
            "</witsml:activity>",
            f"<witsml:unreadField>{payload.text}</witsml:unreadField></witsml:activity>",
        )
        path = tmp_path / suite.FIXTURE_REPORT_NAME
        path.write_text(xml, encoding="utf-8")
        event = next(iter(extract_from_report(path)))

        results = list(suite._extraction_results(payload, event))
        assert [r.outcome for r in results] == [Outcome.NOT_REACHED]
        assert payload.marker in results[0].detail

    def test_a_report_producing_no_event_is_not_reached(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ201"]
        results = list(suite._extraction_results(payload, None))
        assert results[0].outcome is Outcome.NOT_REACHED
        assert "no non-productive event" in results[0].detail

    def test_an_unpublished_payload_is_not_reached_at_the_publication_layer(
        self, control: suite.InvestigationArm
    ) -> None:
        # A payload appended as its own trailing sentence is never quoted, because the controller
        # selects the first sentence carrying a query term. This is the finding that produced the
        # CARRIER docstring, kept as a test so the two cannot drift apart.
        payload = MARKERS["VOLVEINJ201"]
        appended = f"{suite.BENIGN_COMMENT} {payload.text}"
        treated = suite.InvestigationArm(appended)
        assert payload.reached(treated.text)
        assert suite._where_it_landed(treated, payload) == ()

        results = [
            r
            for r in suite._investigation_results(payload, control, treated)
            if r.invariant == "markup_inert"
        ]
        assert [r.outcome for r in results] == [Outcome.NOT_REACHED]

    def test_a_not_reached_result_must_say_what_happened(self) -> None:
        with pytest.raises(ValueError, match="carries no detail"):
            Result(invariant="markup_inert", payload="p", outcome=Outcome.NOT_REACHED, detail="  ")

    def test_the_carrier_does_place_the_payload_where_it_is_published(self) -> None:
        payload = MARKERS["VOLVEINJ201"]
        treated = suite.InvestigationArm(suite.payloaded(payload))
        landed = suite._where_it_landed(treated, payload)
        assert landed, "the carrier no longer reaches the published artifacts"
        assert all(place.endswith("span") for place in landed)


class TestExtractionInvariantsCanFail:
    def test_a_sanitising_extractor_violates_the_verbatim_record(self, tmp_path: Path) -> None:
        # Extraction is a recording consumer. Silently rewriting evidence is worse than keeping
        # it, because the span is quoted to an operator as what the document said.
        payload = MARKERS["VOLVEINJ201"]
        event = suite.extract_one(tmp_path, suite.payloaded(payload))
        assert event is not None
        sanitised = event.model_copy(
            update={"comment": event.comment.replace("<script", "[removed]")}
        )
        results = list(suite._extraction_results(payload, sanitised))
        assert any(r.outcome is Outcome.VIOLATED for r in results)

    def test_the_clean_record_holds_the_payload_verbatim(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ201"]
        event = suite.extract_one(tmp_path, suite.payloaded(payload))
        assert event is not None
        assert payload.text in event.comment
        results = list(suite._extraction_results(payload, event))
        assert all(r.outcome is Outcome.HELD for r in results)


class TestInvestigationInvariantsCanFail:
    def test_a_moved_verdict_is_a_violation(self, control: suite.InvestigationArm) -> None:
        payload = MARKERS["VOLVEINJ301"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        other = next(v for v in Verdict if v != control.finding.verdict)
        broken = _Arm(real, finding=real.finding.model_copy(update={"verdict": other}))

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "schema_integrity"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_a_moved_causal_level_is_a_violation(self, control: suite.InvestigationArm) -> None:
        payload = MARKERS["VOLVEINJ306"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        first, *rest = real.finding.hypotheses
        bumped = (
            first.model_copy(
                update={"causal_level": next(c for c in CausalLevel if c != first.causal_level)}
            ),
            *rest,
        )
        broken = _Arm(real, finding=real.finding.model_copy(update={"hypotheses": bumped}))

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "schema_integrity"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_a_query_the_document_chose_is_a_violation(
        self, control: suite.InvestigationArm
    ) -> None:
        payload = MARKERS["VOLVEINJ501"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        broken = _Arm(real, queries=(f"attacker chosen {payload.marker}",))

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "parameter_bounds"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]
        assert payload.marker in results[0].detail

    def test_an_added_stage_is_a_violation(self, control: suite.InvestigationArm) -> None:
        payload = MARKERS["VOLVEINJ102"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        broken = _Arm(real, stages=(*real.trace.stages, Stage.RETRIEVE_EVIDENCE))

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "fixed_stage_sequence"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_a_dropped_provenance_stage_is_a_violation(
        self, control: suite.InvestigationArm
    ) -> None:
        payload = MARKERS["VOLVEINJ104"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        without = tuple(s for s in real.trace.stages if s is not Stage.VALIDATE_PROVENANCE)
        broken = _Arm(real, stages=without)

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "grounding_and_gating"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_a_moved_fact_anchor_is_a_violation(self, control: suite.InvestigationArm) -> None:
        payload = MARKERS["VOLVEINJ302"]
        real = suite.InvestigationArm(suite.payloaded(payload))
        broken = _Arm(
            real,
            finding=real.finding.model_copy(update={"shortfall_fact_id": "fact_999999"}),
        )

        results = [
            r
            for r in suite._investigation_results(payload, control, broken)
            if r.invariant == "grounding_and_gating"
        ]
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_the_closed_query_map_is_what_the_clean_run_uses(
        self, control: suite.InvestigationArm
    ) -> None:
        from volve_ops.investigation.controller import RuleBasedJudgement

        terms = set(RuleBasedJudgement._TERMS.values())
        for query in control.queries():
            assert query in terms, f"query {query!r} came from outside the closed term map"


class TestFileAccessInvariantCanFail:
    def test_a_denied_open_is_a_violation(self) -> None:
        payload = MARKERS["VOLVEINJ404"]
        with observing(payload.marker) as recorder, contextlib.suppress(OSError):
            Path("/etc/passwd").read_text()
        denied = [e.target for e in recorder.denied_opens()]
        assert denied, "the audit hook saw no open of a denied path"
        result = suite._file_access_results(payload, (), denied)
        assert result.outcome is Outcome.VIOLATED

    def test_a_clean_window_holds(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ401"]
        with observing(payload.marker) as recorder:
            suite.extract_one(tmp_path, suite.payloaded(payload))
        assert recorder.denied_opens() == ()
        result = suite._file_access_results(
            payload, recorder.outside([tmp_path]), [e.target for e in recorder.denied_opens()]
        )
        assert result.outcome is Outcome.HELD

    def test_the_hook_records_network_reach(self) -> None:
        import socket

        with observing("net") as recorder, contextlib.suppress(OSError):
            socket.getaddrinfo("localhost", 1)
        assert recorder.network_reach(), "the audit hook saw no name resolution"

    def test_interpreter_territory_is_classified_out(self) -> None:
        from volve_ops.security.observation import is_interpreter_territory

        assert is_interpreter_territory("/x/site-packages/pydantic/main.py")
        assert is_interpreter_territory("/x/__pycache__/y.pyc")
        assert not is_interpreter_territory("/Users/x/project/data/cache/run.json")


class TestStructuralLanding:
    def test_a_payload_in_a_dict_key_is_a_violation(self) -> None:
        payload = MARKERS["VOLVEINJ201"]
        found = [
            f"{path}:key"
            for path, value, is_key in suite._walk({payload.text: "x"})
            if payload.marker in value and is_key
        ]
        assert found == [f"{payload.text}:key"]
        # A `:key` suffix can never match a free-text field name, so it is always structural.
        assert not found[0].endswith(tuple(suite.FREE_TEXT_FIELDS))

    def test_free_text_paths_are_not_structural(self) -> None:
        assert "finding.hypotheses.0.supporting.0.span".endswith(tuple(suite.FREE_TEXT_FIELDS))


class TestTheWholeSuite:
    """The clean run, after everything above has shown the checks can fail."""

    @pytest.fixture(scope="class")
    def report(self, tmp_path_factory: pytest.TempPathFactory) -> Report:
        return suite.run(tmp_path_factory.mktemp("injection"))

    def test_no_invariant_is_violated(self, report: Report) -> None:
        assert report.violated == 0, [(r.invariant, r.payload, r.detail) for r in report.failures()]

    def test_every_fixture_reached_its_consumer(self, report: Report) -> None:
        assert report.not_reached == 0, [
            (r.invariant, r.payload, r.detail)
            for r in report.failures()
            if r.outcome is Outcome.NOT_REACHED
        ]

    def test_every_live_invariant_was_exercised(self, report: Report) -> None:
        assert unexercised_live_invariants(report.results) == ()

    def test_the_three_vacuous_invariants_are_reported_as_vacuous(self, report: Report) -> None:
        assert report.vacuous == 3
        assert report.summary()["invariants_declared_vacuous"] == 3

    def test_the_run_passes(self, report: Report) -> None:
        assert report.passed is True

    def test_every_payload_produced_at_least_one_result(self, report: Report) -> None:
        judged = {r.payload for r in report.results}
        for payload in ALL_PAYLOADS:
            assert payload.name in judged, f"{payload.name} produced no result at all"


class TestTheMarkupSinkGate:
    """Section 22.4 mark 2. A source check, because no payload can reach a sink no screen has."""

    def test_the_frontend_has_no_unescaped_markup_sink(self) -> None:
        from volve_ops.security.sinks import scan

        assert scan() == ()

    def test_the_gate_reports_what_it_read(self) -> None:
        # A scan of nothing passes, so the file count is part of the result. Section 21.2 records
        # what happens when a mark that examined nothing is read as a mark that passed.
        from volve_ops.security.sinks import files_scanned

        read = files_scanned()
        assert len(read) >= 8
        assert any(name.endswith("App.tsx") for name in read)

    def test_the_gate_finds_a_sink_when_one_exists(self, tmp_path: Path) -> None:
        from volve_ops.security.sinks import scan

        (tmp_path / "Bad.tsx").write_text(
            "export const B = () => <h1 dangerously" + "SetInnerHTML={{__html: x}} />;\n",
            encoding="utf-8",
        )
        found = scan(tmp_path)
        assert len(found) == 1
        assert found[0].sink == "dangerouslySetInnerHTML"
        assert found[0].line == 1

    def test_the_gate_scans_comments_too(self, tmp_path: Path) -> None:
        # Deliberately no exceptions: a sink inside something shaped like a comment is still
        # reported, because a gate with an exception list is a gate someone will add to.
        from volve_ops.security.sinks import scan

        (tmp_path / "Note.tsx").write_text(
            "// we never use inner" + "HTML here\n", encoding="utf-8"
        )
        assert len(scan(tmp_path)) == 1


class TestTheAttackCorpus:
    """Section 22.4 mark 5 and section 22.5. The defences exist; this attacks them."""

    @pytest.mark.parametrize("attack", XML_ATTACKS, ids=lambda a: a.name)
    def test_every_xml_attack_is_refused(self, attack: Attack, tmp_path: Path) -> None:
        from volve_ops.ingest.quarantine import UnsafeInputError
        from volve_ops.ingest.safe_xml import parse_xml_file

        path = attack.build(tmp_path)
        with pytest.raises(UnsafeInputError) as refusal:
            # The size bound is lowered so the oversized fixture need not be eight mebibytes.
            # Every other fixture is far below it, so the lowered bound changes nothing for them.
            parse_xml_file(path, max_bytes=10_000)
        message = str(refusal.value).lower()
        for expected in attack.expect_refusal_mentioning:
            assert expected in message, f"{attack.name}: refusal said {message!r}"

    @pytest.mark.parametrize("attack", ARCHIVE_ATTACKS, ids=lambda a: a.name)
    def test_every_archive_attack_is_refused(self, attack: Attack, tmp_path: Path) -> None:
        from volve_ops.ingest.quarantine import UnsafeInputError
        from volve_ops.ingest.safe_archive import safe_extract_zip

        archive = attack.build(tmp_path)
        destination = tmp_path / "out"
        with pytest.raises(UnsafeInputError) as refusal:
            safe_extract_zip(
                archive,
                destination,
                # Lowered so a bomb fixture is kilobytes rather than gigabytes. This tests the
                # comparison; the constants themselves are asserted separately below.
                max_total_bytes=1_000_000,
                max_member_bytes=500_000,
                max_members=20,
                max_ratio=50.0,
            )
        message = str(refusal.value).lower()
        for expected in attack.expect_refusal_mentioning:
            assert expected in message, f"{attack.name}: refusal said {message!r}"

    def test_the_real_budgets_are_what_the_protocol_says(self) -> None:
        # The bombs above run against lowered budgets, so the production constants are checked
        # here. Without this the suite would prove a comparison works and say nothing about the
        # numbers the system actually runs with.
        from volve_ops.ingest import safe_archive, safe_xml

        assert safe_xml.MAX_XML_BYTES == 8 * 1024 * 1024
        assert safe_archive.MAX_UNCOMPRESSED_BYTES == 32 * 1024 * 1024 * 1024
        assert safe_archive.MAX_MEMBER_BYTES == 4 * 1024 * 1024 * 1024
        assert safe_archive.MAX_MEMBERS == 100_000
        assert safe_archive.MAX_COMPRESSION_RATIO == 900.0

    def test_nothing_was_written_when_an_archive_is_refused(self, tmp_path: Path) -> None:
        from volve_ops.ingest.quarantine import UnsafeInputError
        from volve_ops.ingest.safe_archive import safe_extract_zip

        archive = _relative_escape_fixture(tmp_path)
        destination = tmp_path / "out"
        with pytest.raises(UnsafeInputError):
            safe_extract_zip(archive, destination)
        assert not (tmp_path.parent / "escaped.xml").exists()
        assert not list(destination.glob("**/*")) if destination.exists() else True

    @pytest.mark.parametrize("attack", XML_ATTACKS, ids=lambda a: a.name)
    def test_a_refusal_does_not_relax_the_next_file(self, attack: Attack, tmp_path: Path) -> None:
        """Section 22.4 mark 5's second clause.

        A parser that disabled a check after refusing something, or cached a permissive
        configuration, would pass every fixture above and fail here. The valid file is parsed
        immediately after each refusal and must still get the whole check set, which is shown by
        feeding it a document that only the full set refuses.
        """
        from volve_ops.ingest.quarantine import UnsafeInputError
        from volve_ops.ingest.safe_xml import parse_xml_file

        with pytest.raises(UnsafeInputError):
            parse_xml_file(attack.build(tmp_path), max_bytes=10_000)

        good = tmp_path / "good.xml"
        good.write_text('<?xml version="1.0"?><drillReport><a/></drillReport>', encoding="utf-8")
        assert parse_xml_file(good).tag == "drillReport"

        # And the full check set still runs: an entity document offered right after a refusal is
        # still refused, rather than slipping through a parser left in a relaxed state.
        again = tmp_path / "again.xml"
        again.write_text(
            '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x "y">]><r>&x;</r>', encoding="utf-8"
        )
        with pytest.raises(UnsafeInputError):
            parse_xml_file(again)

    @pytest.mark.parametrize("case", PARSES_CORRECTLY, ids=lambda a: a.name)
    def test_an_odd_but_harmless_document_is_read_correctly(
        self, case: Attack, tmp_path: Path
    ) -> None:
        """A corpus of things that must fail cannot tell a careful parser from a broken one.

        The encoding-mismatch document declares UTF-8 and is written in UTF-16. It is not an
        attack on this parser, because `safe_xml` refuses constructs rather than filtering
        content, so there is no content filter for a re-encoding to slip past. What matters is
        that the text comes back right.
        """
        from volve_ops.ingest.safe_xml import parse_xml_file

        root = parse_xml_file(case.build(tmp_path), max_bytes=10_000)
        assert root.tag == "r"
        assert root.text == "drilling"

    def test_every_fixture_names_an_unreachable_path(self) -> None:
        # A fixture pointing at /etc/passwd that succeeded would look like a test that passed.
        from volve_ops.security.attacks import UNREACHABLE

        assert not Path(UNREACHABLE).exists()
        assert not Path(UNREACHABLE).parent.exists()


def _relative_escape_fixture(directory: Path) -> Path:
    from volve_ops.security.attacks import ARCHIVE_ATTACKS

    return next(a for a in ARCHIVE_ATTACKS if a.name == "relative-escape").build(directory)
