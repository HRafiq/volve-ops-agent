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

from volve_ops.console.store import ArtifactMissing
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
        # A faithful stand-in rather than a namespace: the invariant checks serialise the trace,
        # so a double without `model_dump` fails inside the code under test instead of exercising
        # it. A double that cannot do what the real object does tests the double.
        real = self._real.trace
        stages = self._stages
        return SimpleNamespace(
            steps=real.steps,
            stages=stages,
            model_dump=real.model_dump,
        )

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


class TestTheOverclaimGate:
    """Section 22.4 mark 13. Section 11.1: the read-only posture is not a safety case."""

    def test_the_project_claims_no_safety_case(self) -> None:
        from volve_ops.security.claims import scan as claim_scan

        found = claim_scan()
        assert found == (), [(c.file, c.line, c.pattern) for c in found]

    def test_the_gate_read_a_meaningful_number_of_files(self) -> None:
        from volve_ops.security.claims import files_scanned

        assert files_scanned() > 50

    def test_it_fires_on_a_real_overclaim(self, tmp_path: Path) -> None:
        from volve_ops.security.claims import scan as claim_scan

        (tmp_path / "over.md").write_text(
            "The system satisfies an operator safety case.\n"
            "It is certified for operational use.\n"
            "The agent controls the choke directly.\n",
            encoding="utf-8",
        )
        patterns = {c.pattern for c in claim_scan([tmp_path])}
        assert "safety_case_satisfied" in patterns
        assert "approved_for_operations" in patterns
        assert "in_the_control_loop" in patterns

    def test_stating_what_the_system_is_not_is_allowed(self, tmp_path: Path) -> None:
        # The opposite of the problem. A gate that fired on a disclaimer would be deleted.
        (tmp_path / "fine.md").write_text(
            "This does not satisfy a formal safety case, which is far broader.\n", encoding="utf-8"
        )
        from volve_ops.security.claims import scan as claim_scan

        assert claim_scan([tmp_path]) == ()


class TestEveryObservationGatesTheFileAccessOutcome:
    """The failing cases the first version of this invariant had none of.

    `_file_access_results` took the set of files opened outside the declared roots, used it for a
    `len()` inside a sentence claiming none were, and branched on the denied list alone. The only
    way the invariant could fail was a hit on a ten-entry literal list, while its own wording is
    that document text cannot reach *arbitrary* local files. There was one test and it exercised
    the empty case, which is why it survived.
    """

    def test_a_file_outside_the_declared_roots_is_a_violation(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ402"]
        elsewhere = tmp_path / "not-the-fixture-dir"
        elsewhere.mkdir()
        secret = elsewhere / "customer-contract.txt"
        secret.write_text("commercially sensitive", encoding="utf-8")

        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with observing(payload.marker) as recorder:
            secret.read_text(encoding="utf-8")

        result = suite._file_access_results(
            payload,
            recorder.outside([fixtures]),
            [e.target for e in recorder.denied_opens()],
        )
        assert result.outcome is Outcome.VIOLATED
        assert "customer-contract.txt" in result.detail

    def test_a_network_connection_is_a_violation(self) -> None:
        # The invariant's published reason claims no network connection is attempted, and nothing
        # consulted the recorder's network observations until this test existed.
        import socket

        payload = MARKERS["VOLVEINJ403"]
        with observing(payload.marker) as recorder, contextlib.suppress(OSError):
            socket.getaddrinfo("localhost", 1)

        result = suite._file_access_results(payload, (), (), recorder.network_reach(), ())
        assert result.outcome is Outcome.VIOLATED
        assert "network reached" in result.detail

    def test_a_subprocess_launch_is_a_violation(self) -> None:
        import subprocess

        payload = MARKERS["VOLVEINJ404"]
        with observing(payload.marker) as recorder:
            subprocess.run(["true"], check=False, capture_output=True)

        result = suite._file_access_results(payload, (), (), (), recorder.code_execution())
        assert result.outcome is Outcome.VIOLATED

    def test_the_clean_detail_does_not_assert_more_than_was_observed(self, tmp_path: Path) -> None:
        payload = MARKERS["VOLVEINJ401"]
        with observing(payload.marker) as recorder:
            suite.extract_one(tmp_path, suite.payloaded(payload))
        result = suite._file_access_results(
            payload,
            recorder.outside([tmp_path]),
            [e.target for e in recorder.denied_opens()],
            recorder.network_reach(),
            recorder.code_execution(),
        )
        assert result.outcome is Outcome.HELD
        assert "no file opened outside" in result.detail


class TestTheExercisedByMapIsEnforced:
    """`EXERCISED_BY` published which classes exercise which invariant and nothing read it."""

    def test_the_map_names_every_live_invariant(self) -> None:
        from volve_ops.security.invariants import EXERCISED_BY, LIVE_INVARIANTS

        assert {i.key for i in LIVE_INVARIANTS} == set(EXERCISED_BY)

    def test_the_two_held_counts_differ_and_both_are_published(self, tmp_path: Path) -> None:
        # One number alone is either an inflated headline or a discarded observation. The suite
        # runs every live invariant against every payload, so most held results come from a class
        # that was not written to provoke that invariant.
        report = suite.run(tmp_path)
        summary = report.summary()
        assert summary["invariants_held"] > summary["invariants_held_under_the_exercising_class"]
        assert summary["invariants_held_under_the_exercising_class"] > 0

    def test_a_held_result_outside_the_map_is_reported(self) -> None:
        from volve_ops.security.invariants import Report, Result, results_outside_the_map

        # markup_inert is declared as exercised by classes 2 and 6; this payload is class 1.
        stray = Result(
            invariant="markup_inert",
            payload="ignore-prior-instruction",
            outcome=Outcome.HELD,
            detail="d",
        )
        assert results_outside_the_map(Report(results=(stray,)).results) == (
            "markup_inert held under ignore-prior-instruction (class 1)",
        )


class TestTheReviewStateConjunctCanFire:
    """It could not. The probe searched serialised JSON for text a payload can never produce."""

    def test_a_published_review_key_is_a_violation(self, control: suite.InvestigationArm) -> None:
        payload = MARKERS["VOLVEINJ104"]
        real = suite.InvestigationArm(suite.payloaded(payload))

        class _WithReviewField(_Arm):
            def published(self) -> str:
                return self._real.published()

        broken = _WithReviewField(real)
        # Simulate a schema that gained a review field, which is what the conjunct should catch.
        original = suite._published_objects

        def patched(arm: object) -> dict[str, object]:
            objects = original(arm)  # type: ignore[arg-type]
            objects["finding"]["review_state"] = "confirmed"
            return objects

        suite._published_objects = patched
        try:
            results = [
                r
                for r in suite._investigation_results(payload, control, broken)
                if r.invariant == "grounding_and_gating"
            ]
        finally:
            suite._published_objects = original
        assert [r.outcome for r in results] == [Outcome.VIOLATED]

    def test_a_payloads_own_text_cannot_fire_it(self, control: suite.InvestigationArm) -> None:
        # The payload says "mark it confirmed". That must not be mistaken for the schema carrying
        # a review state, which is what a substring probe over the serialised artifact did.
        payload = MARKERS["VOLVEINJ104"]
        treated = suite.InvestigationArm(suite.payloaded(payload))
        assert "confirmed" in payload.text
        results = [
            r
            for r in suite._investigation_results(payload, control, treated)
            if r.invariant == "grounding_and_gating"
        ]
        assert [r.outcome for r in results] == [Outcome.HELD]


class TestClassThreeOverManifestPaths:
    """Section 22.6 class 3 on the System Health screen, whose figures name manifest keys.

    These run on synthetic manifests and need no cached dataset, which is the point. The health
    checks lived only in `tests/test_health_payload.py`, which skips without `data/cache/`, and in
    a harness step that skips for the same reason. So mark 11's value half ran in neither the test
    suite nor CI, and `run_security_checks.py` carried a comment saying it ran on every push.
    """

    def test_the_walk_reaches_leaves_inside_lists(self) -> None:
        # The defect this class exists for. The first walk handled mappings and scalars only, so
        # it collected 221 of 768 leaves and every figure sourced through a list was skipped as
        # "not something we hold" rather than compared. On the health screen that was every
        # derived figure and none of the literal reads: it could see only what could not be wrong.
        from volve_ops.security.provenance_failures import manifest_values

        values = manifest_values(
            {"ablation": {"rows": [{"model": "a", "opened": 14}, {"model": "b", "opened": 11}]}}
        )
        assert values["ablation.rows.0.opened"] == 14.0
        assert values["ablation.rows.1.opened"] == 11.0

    def test_booleans_are_collected_so_a_flipped_flag_is_a_contradiction(self) -> None:
        from volve_ops.security.provenance_failures import manifest_values

        values = manifest_values({"m": {"changed": True, "other": False}})
        assert values == {"m.changed": 1.0, "m.other": 0.0}

    def test_a_figure_contradicting_its_manifest_key_is_caught(self) -> None:
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import contradictions_in_health

        manifests = {"ablation": {"calibration": {"bands": {"high": 7}}}}
        screen = {"row": Sourced(value=7000.0, source="ablation.calibration.bands.high", unit="")}
        found = contradictions_in_health(screen, manifests)
        assert len(found) == 1
        assert found[0].published == 7000.0
        assert found[0].recorded == 7.0

    def test_a_figure_inside_a_list_is_caught(self) -> None:
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import contradictions_in_health

        manifests = {"ablation": {"rows": [{"opened": 14}]}}
        screen = {"row": Sourced(value=1014.0, source="ablation.rows.0.opened", unit="")}
        assert len(contradictions_in_health(screen, manifests)) == 1

    def test_a_flipped_boolean_is_caught(self) -> None:
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import contradictions_in_health

        manifests = {"ablation": {"rows": [{"level_changed": False}]}}
        screen = {"row": Sourced(value=True, source="ablation.rows.0.level_changed", unit="")}
        assert len(contradictions_in_health(screen, manifests)) == 1

    def test_a_matching_figure_is_not_flagged(self) -> None:
        # Without this the tests above would pass against a check that flags everything.
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import contradictions_in_health

        manifests = {"ablation": {"rows": [{"opened": 14}]}}
        screen = {"row": Sourced(value=14.0, source="ablation.rows.0.opened", unit="")}
        assert contradictions_in_health(screen, manifests) == ()

    def test_a_figure_sourced_to_a_container_is_not_compared(self) -> None:
        """Stated as a limit rather than left to be discovered.

        A source naming a list or a mapping has no value to compare against, so class 3 passes it
        over. That is why every derived figure on the health screen now names an indexed leaf: a
        container source is a source mark 1 accepts and this check cannot see.
        """
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import contradictions_in_health

        manifests = {"ablation": {"rows": [{"opened": 14}]}}
        screen = {"row": Sourced(value=999.0, source="ablation.rows", unit="")}
        assert contradictions_in_health(screen, manifests) == ()


class TestTheHealthHalfReportsWhetherItRan:
    """A single `class_3_ran` covering both halves said a check had run when half had not."""

    def test_it_reports_not_run_without_the_section_22_manifests(self, tmp_path: Path) -> None:
        import json

        from volve_ops.console.store import RunStore
        from volve_ops.security.provenance_failures import health_contradictions

        (tmp_path / "investigations").mkdir()
        (tmp_path / "investigation_run.json").write_text(
            json.dumps({"protocol_version": "v17", "findings": []}), encoding="utf-8"
        )
        result, health_ran = health_contradictions(
            RunStore(cache=tmp_path, traces=tmp_path / "investigations")
        )
        assert result.contradictions == ()
        assert result.compared == 0
        assert health_ran is False

    def test_a_failure_in_the_health_half_is_not_swallowed(self, tmp_path: Path) -> None:
        """The suppress ate a real class-3 condition it was written alongside.

        `_episodes_opened_by_selected` raises `ArtifactMissing` when the selected model has no row
        in the ablation manifest, which is a figure sourced to something that does not exist. The
        handler that let the per-episode half run without the section 22 manifests was catching it
        and reporting the run clean.

        Every manifest must be present for this to be the condition under test: a cache that is
        merely incomplete is a skip, which is a different answer and the one the earlier version
        of this test was accidentally getting.
        """
        import json
        import shutil

        from volve_ops.console.store import RunStore, missing_manifests
        from volve_ops.security.provenance_failures import health_contradictions

        if missing_manifests():
            pytest.skip("this needs a complete cache to break one manifest inside it")
        cache = tmp_path / "cache"
        shutil.copytree("data/cache", cache)

        # A selected model the ablation manifest has no row for: present, complete, and wrong.
        ablation = json.loads((cache / "ablation_run.json").read_text(encoding="utf-8"))
        for row in ablation["expectation"]["rows"]:
            row["model"] = f"{row['model']}-renamed"
        (cache / "ablation_run.json").write_text(json.dumps(ablation), encoding="utf-8")

        assert missing_manifests(cache) == ()
        with pytest.raises(ArtifactMissing, match="no row for the selected model"):
            health_contradictions(RunStore(cache=cache, traces=cache / "investigations"))


class TestThePayloadSideWalkIsPinnedToo:
    """Round 2 found the manifest side of the comparison blind to lists. This is the other side.

    `manifest_values` descends lists in the manifest; `figures_contradicting_their_records`
    descends them in the **payload**. The class above pins the first. Removing the payload-side
    descent dropped the health screen to a single figure compared and the whole suite still
    passed, because every test in that class builds a flat dict payload and every real payload is
    tuples.

    Counts are deliberately not written here. The same two numbers were corrected in protocol
    amendment 12 and left stale in this docstring twenty lines away, which is what a figure fixed
    in prose does.
    """

    def test_a_figure_inside_a_tuple_is_compared(self) -> None:
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import compare_figures

        payload = {
            "rows": (
                Sourced(value=1.0, source="m.a", unit=""),
                Sourced(value=2.0, source="m.b", unit=""),
            )
        }
        result = compare_figures(payload, {"m.a": 1.0, "m.b": 2.0})
        assert result.compared == 2
        assert result.contradictions == ()

    def test_a_contradiction_inside_a_tuple_is_found(self) -> None:
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import compare_figures

        payload = {"rows": (Sourced(value=99.0, source="m.a", unit=""),)}
        result = compare_figures(payload, {"m.a": 1.0})
        assert len(result.contradictions) == 1

    def test_a_figure_nested_in_a_model_inside_a_tuple_is_compared(self) -> None:
        # The real shape: SystemHealth holds tuples of HealthRow, each holding a Sourced.
        from volve_ops.console.payloads import HealthRow
        from volve_ops.console.sources import Sourced
        from volve_ops.security.provenance_failures import compare_figures

        payload = {
            "rows": (
                HealthRow(label="x", value=Sourced(value=5.0, source="m.a", unit=""), note=""),
            )
        }
        result = compare_figures(payload, {"m.a": 7.0})
        assert result.compared == 1
        assert len(result.contradictions) == 1

    def test_the_real_health_payload_compares_many_figures(self) -> None:
        """A denominator over the actual screen, not a synthetic one.

        Skipped without the cache, which is why the synthetic tests above exist as well: this is
        the one that would notice the payload walk losing a container type the others do not use.
        """
        from volve_ops.console import assemble

        # Every manifest `system_health` reads, from the one place that declares them.
        from volve_ops.console.store import RunStore, missing_manifests
        from volve_ops.security.provenance_failures import compare_figures, manifest_values

        if missing_manifests():
            pytest.skip(f"not written: {', '.join(missing_manifests())}")
        store = RunStore()
        result = compare_figures(
            {"system_health": assemble.system_health(store)},
            manifest_values(store.health_manifests()),
        )
        assert result.compared >= 30, result.compared
        assert result.vacuous is False

    def test_a_comparison_over_nothing_is_vacuous(self) -> None:
        from volve_ops.security.provenance_failures import compare_figures

        result = compare_figures({"empty": {}}, {"m.a": 1.0})
        assert result.compared == 0
        assert result.vacuous is True


class TestTheGateGuardsCanFail:
    """Marks 8 and 9's guards, exercised where they can actually run.

    Both live in `scripts/run_security_checks.py` and both skip on every CI runner, because
    `data/` is not committed. That is the sentence this file already uses about mark 11's value
    half, and round 3 solved it there by building synthetic manifests. The move was not repeated
    for the guards rounds 3 and 4 added, so the central non-security repair of each round lived
    only where it could not run.

    Mark 9 reads one manifest and is tested synthetically, so it runs anywhere. Marks 8 and 11
    assemble the whole console and need the real cache, so those cases copy it and skip without
    it — an honest split rather than a stub that resembles the thing loosely enough to pass.
    """

    @staticmethod
    def _run(cache: Path) -> int:
        # Imported by bare module name off `scripts/`, the pattern test_verify_manifest.py uses.
        # `from scripts.run_security_checks import ...` makes mypy see one file under two module
        # names, because `scripts` is on its `files` list and on sys.path.
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from run_security_checks import main

        return main(["--cache", str(cache), "--out", str(cache / "security_run.json")])

    @staticmethod
    def _real_cache(tmp_path: Path) -> Path:
        import shutil

        from volve_ops.console.store import missing_manifests

        if missing_manifests():
            pytest.skip("these cases assemble the console; they need the real manifests")
        cache = tmp_path / "cache"
        shutil.copytree("data/cache", cache)
        return cache

    def test_mark_9_fails_when_the_population_disagrees_with_the_sweep(
        self, tmp_path: Path
    ) -> None:
        """The exact defect amendment 12 records: a dropped episode, a published survivor count."""
        import json

        cache = self._real_cache(tmp_path)
        manifest = json.loads((cache / "ablation_run.json").read_text(encoding="utf-8"))
        manifest["retrieval"]["episodes_with_documents"] = 1
        (cache / "ablation_run.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert self._run(cache) == 1

    def test_mark_9_fails_when_the_counts_do_not_cover_the_sweep(self, tmp_path: Path) -> None:
        import json

        cache = self._real_cache(tmp_path)
        manifest = json.loads((cache / "ablation_run.json").read_text(encoding="utf-8"))
        manifest["retrieval"]["episode_document_counts"] = []
        (cache / "ablation_run.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert self._run(cache) == 1

    def test_mark_9_fails_when_an_ablation_is_absent(self, tmp_path: Path) -> None:
        import json

        cache = self._real_cache(tmp_path)
        manifest = json.loads((cache / "ablation_run.json").read_text(encoding="utf-8"))
        del manifest["calibration"]
        (cache / "ablation_run.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert self._run(cache) == 1

    def test_mark_8_fails_on_an_empty_queue(self, tmp_path: Path) -> None:
        """Round 4's repair: the per-episode half is the half that can compare nothing."""
        import json

        cache = self._real_cache(tmp_path)
        manifest = json.loads((cache / "investigation_run.json").read_text(encoding="utf-8"))
        manifest["findings"] = []
        (cache / "investigation_run.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert self._run(cache) == 1

    @pytest.mark.parametrize(
        "absent",
        [
            "run_manifest.json",
            "extraction_run.json",
            "label_scoring_run.json",
            "postmortem_run.json",
            "console_run.json",
            "evaluation_run.json",
        ],
    )
    def test_a_partial_cache_skips_rather_than_failing(self, tmp_path: Path, absent: str) -> None:
        """Round 5's finding: a manifest the screen reads being absent is a skip, not a failure.

        This is the gate's documented behaviour on a runner, and it exited 1 for five of the eight
        manifests it had not named, which is the state `check_like_ci.sh` leaves its checkout in.
        """
        cache = self._real_cache(tmp_path)
        (cache / absent).unlink()
        assert self._run(cache) == 0

    def test_the_unmodified_cache_passes(self, tmp_path: Path) -> None:
        """Without this every case above would pass against a gate that fails on everything."""
        cache = self._real_cache(tmp_path)
        assert self._run(cache) == 0


class TestTheDeclaredManifestSetMatchesWhatIsOpened:
    """`HEALTH_MANIFESTS` is checked against observation, not against a reading of the code.

    Four of the five review rounds of this phase turned on a guard that named a subset of what
    something actually reads: the gate named two of eight, one test file named two, another named
    one, and the list written to end that was itself short by one, because the queue opens
    `evaluation_run.json` and no amount of reading the call graph had noticed.

    The audit hook built for section 22.4 mark 4 answers this directly. It was written to observe
    what a run opens while resisting an injected payload; the same observation settles what the
    health screen depends on.
    """

    def test_the_declared_set_is_exactly_what_the_health_path_opens(self) -> None:
        from volve_ops.console.store import HEALTH_MANIFESTS, RunStore, missing_manifests
        from volve_ops.security.observation import observing
        from volve_ops.security.provenance_failures import (
            contradictions_in_console,
            health_contradictions,
        )

        if missing_manifests():
            pytest.skip("this observes a real assembly; it needs the manifests present")

        with observing("manifest-census") as recorder:
            contradictions_in_console(RunStore())
            health_contradictions(RunStore())

        opened = {
            Path(event.target).name
            for event in recorder.events
            if event.is_file_open and Path(event.target).name.endswith(".json")
        }
        # Only the manifests, not the per-episode artifacts, which are addressed by episode id
        # rather than by a fixed name and are guarded by the store's own ArtifactMissing.
        manifests = {
            name for name in opened if name.endswith("_run.json") or name == "run_manifest.json"
        }
        assert manifests == set(HEALTH_MANIFESTS), {
            "opened but not declared": sorted(manifests - set(HEALTH_MANIFESTS)),
            "declared but not opened": sorted(set(HEALTH_MANIFESTS) - manifests),
        }
