"""The operator console's backend, against protocol section 21.

Section 21.1 is the rule everything here serves: the console renders and does not compute. So these
tests are mostly about refusal and fidelity rather than about arithmetic, and the arithmetic that
does exist, the priority rule, is tested against the rule as section 21.5 prints it rather than
against the implementation's own output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from volve_ops.console import assemble, gates, priority
from volve_ops.console.payloads import ChartSeries, EvidenceCoverage, Money
from volve_ops.console.review import Action, ReviewLog, ReviewRecord, ReviewRefused
from volve_ops.console.sources import Sourced
from volve_ops.domain.activity import activity_dates_by_well
from volve_ops.domain.day_class import DayClass
from volve_ops.domain.episodes import (
    MIN_TRIGGER_RUN,
    Episode,
    SeriesPoint,
    sweep_series,
    sweep_well,
)
from volve_ops.domain.expectation import NaiveMedian28
from volve_ops.domain.production_service import load_volve_production
from volve_ops.domain.regimes import stable_reference_windows
from volve_ops.domain.splits import derive_split, development_only

MANIFEST = Path("data/cache/investigation_run.json")
EVALUATION = Path("data/cache/evaluation_run.json")
WORKBOOK = Path("data/cache/Volve production data.xlsx")
REPORTS = Path("data/cache/ddr_xml")


def episode(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "well": "15/9-F-12",
        "onset": "2010-01-14",
        "cumulative_shortfall_sm3": 5_000.0,
        "episode_days": 10,
        "verdict": "supported_explanation",
        "evidence_band": "high",
        "review_state": "none",
    }
    base.update(over)
    return base


class TestThePriorityRule:
    """Section 21.5, and ADR 0009's account of what it is worth."""

    def test_the_three_shortfall_levels_are_the_pre_registered_ones(self) -> None:
        assert priority.shortfall_points(30_000.0) == 3
        assert priority.shortfall_points(29_999.99) == 2
        assert priority.shortfall_points(10_000.0) == 2
        assert priority.shortfall_points(9_999.99) == 1
        assert priority.shortfall_points(0.0) == 1

    def test_the_band_cut_offs_are_the_pre_registered_ones(self) -> None:
        assert priority.band_of(5) is priority.Priority.HIGH
        assert priority.band_of(4) is priority.Priority.MEDIUM
        assert priority.band_of(3) is priority.Priority.MEDIUM
        assert priority.band_of(2) is priority.Priority.LOW

    def test_an_unresolved_verdict_raises_priority_only_in_an_attention_band(self) -> None:
        """ADR 0009's decision, which is the one thing the console design left open.

        "No evidence, so no conclusion" is a data-coverage problem and belongs in a filter. A case
        where the evidence was strong and the system still could not choose is where a human adds
        something, and that is the only unresolved case this term fires on.
        """
        strong = priority.score_episode(
            **episode(verdict="insufficient_evidence", evidence_band="moderate")  # type: ignore[arg-type]
        )
        weak = priority.score_episode(
            **episode(verdict="insufficient_evidence", evidence_band="low")  # type: ignore[arg-type]
        )
        assert priority.Term.UNRESOLVED_WITH_EVIDENCE in strong.terms_fired
        assert priority.Term.UNRESOLVED_WITH_EVIDENCE not in weak.terms_fired
        assert strong.score == weak.score + 1

    def test_a_supported_verdict_never_fires_the_unresolved_term(self) -> None:
        for band in ("high", "moderate", "low"):
            scored = priority.score_episode(
                **episode(verdict="supported_explanation", evidence_band=band)  # type: ignore[arg-type]
            )
            assert priority.Term.UNRESOLVED_WITH_EVIDENCE not in scored.terms_fired

    def test_the_duration_term_fires_at_forty_days_and_not_at_thirty_nine(self) -> None:
        assert priority.Term.DURATION in priority.score_episode(
            **episode(episode_days=40)  # type: ignore[arg-type]
        ).terms_fired
        assert priority.Term.DURATION not in priority.score_episode(
            **episode(episode_days=39)  # type: ignore[arg-type]
        ).terms_fired

    @pytest.mark.parametrize("state", ["awaiting_review", "rerun_requested"])
    def test_a_pending_review_raises_priority(self, state: str) -> None:
        scored = priority.score_episode(**episode(review_state=state))  # type: ignore[arg-type]
        assert priority.Term.REVIEW_PENDING in scored.terms_fired

    @pytest.mark.parametrize("state", ["none", "confirmed", "dismissed"])
    def test_a_settled_review_does_not(self, state: str) -> None:
        scored = priority.score_episode(**episode(review_state=state))  # type: ignore[arg-type]
        assert priority.Term.REVIEW_PENDING not in scored.terms_fired

    def test_the_score_is_the_sum_the_rule_prints(self) -> None:
        """Section 21.6 mark 8: the backend's score equals the rule as printed.

        Recomputed from the printed rule rather than from the implementation, so a change to one
        without the other fails here.
        """
        scored = priority.score_episode(
            **episode(  # type: ignore[arg-type]
                cumulative_shortfall_sm3=45_000.0,
                episode_days=66,
                verdict="multiple_plausible_explanations",
                evidence_band="high",
                review_state="awaiting_review",
            )
        )
        assert scored.shortfall_points == 3
        assert len(scored.terms_fired) == 3
        assert scored.score == 6
        assert scored.priority is priority.Priority.HIGH
        assert scored.score == scored.shortfall_points + len(scored.terms_fired)

    def test_every_row_can_explain_its_own_score(self) -> None:
        scored = priority.score_episode(**episode(episode_days=99))  # type: ignore[arg-type]
        assert "shortfall 1" in scored.explanation
        assert "40 days" in scored.explanation

    def test_an_episode_with_no_term_beyond_shortfall_says_so(self) -> None:
        scored = priority.score_episode(**episode())  # type: ignore[arg-type]
        assert scored.terms_fired == ()
        assert "no term beyond shortfall" in scored.explanation

    def test_term_counts_name_every_term_including_the_ones_that_fire_on_nothing(self) -> None:
        """Section 21.5 requires this, and ADR 0009 says why.

        Two of the four terms fire on nothing in a first run, so a reader shown only the rubric
        would credit the rule with judgement it has not made. A term absent from the counts would be
        worse than one reported as zero.
        """
        scored = [priority.score_episode(**episode())]  # type: ignore[arg-type]
        counts = priority.term_counts(scored)
        assert set(counts) == {term.value for term in priority.Term}
        assert counts[priority.Term.REVIEW_PENDING.value] == 0
        assert counts[priority.Term.SHORTFALL.value] == 1


@pytest.mark.skipif(not MANIFEST.exists(), reason="needs a cached investigation run")
class TestThePriorityRuleOnTheRealRun:
    """ADR 0009's measured claims, against the manifests they were measured from."""

    def scored(self) -> list[priority.Scored]:
        findings = json.loads(MANIFEST.read_text(encoding="utf-8"))["findings"]
        bands = {
            (r["well"], r["onset"]): r["band"]
            for r in json.loads(EVALUATION.read_text(encoding="utf-8"))["evidence_scores"]
        }
        return [
            priority.score_episode(
                well=r["well"],
                onset=r["onset"],
                cumulative_shortfall_sm3=r["cumulative_rate_shortfall_sm3"],
                episode_days=r["episode_days"],
                verdict=r["verdict"],
                evidence_band=bands[(r["well"], r["onset"])],
                review_state="none",
            )
            for r in findings
        ]

    def test_the_term_counts_are_the_ones_adr_0009_publishes(self) -> None:
        counts = priority.term_counts(self.scored())
        assert counts[priority.Term.SHORTFALL.value] == 14
        assert counts[priority.Term.DURATION.value] == 5
        assert counts[priority.Term.REVIEW_PENDING.value] == 0
        assert counts[priority.Term.UNRESOLVED_WITH_EVIDENCE.value] == 5

    def test_the_disputed_clause_changes_no_band_on_this_dataset(self) -> None:
        """ADR 0009's central measurement, and why the decision is a convention and not a result.

        The blunt form adds a point for any unresolved verdict. The banded form adds it only in an
        attention band. Neither changes any episode's band here, so this dataset cannot tell the two
        apart, and the console says so instead of implying it was validated.
        """
        findings = json.loads(MANIFEST.read_text(encoding="utf-8"))["findings"]
        banded = {(s.well, s.onset): s.priority for s in self.scored()}
        differ = 0
        for row in findings:
            points = priority.shortfall_points(row["cumulative_rate_shortfall_sm3"])
            extra = 1 if row["episode_days"] >= priority.LONG_EPISODE_DAYS else 0
            blunt = points + extra + (1 if row["verdict"] != priority.SUPPORTED else 0)
            if priority.band_of(blunt) is not banded[(row["well"], row["onset"])]:
                differ += 1
        assert differ == 0

    def test_the_unresolved_term_decides_the_only_high_episode(self) -> None:
        """A first draft of ADR 0009 claimed the rule reduces to shortfall plus duration here.

        This test was written to assert that and failed, which is how the claim was caught. Dropping
        the unresolved term moves `15/9-F-14` from 2009-05-29 out of HIGH and leaves the queue with
        no HIGH case at all, so the term is not inert, even though the choice between its two
        candidate forms is undetectable on this data.
        """
        scored = self.scored()
        reduced = {
            (s.well, s.onset): priority.band_of(
                s.shortfall_points + (1 if priority.Term.DURATION in s.terms_fired else 0)
            )
            for s in scored
        }
        moved = [s for s in scored if s.priority is not reduced[(s.well, s.onset)]]
        assert [(s.well, s.onset) for s in moved] == [("15/9-F-14", "2009-05-29")]
        assert moved[0].priority is priority.Priority.HIGH
        assert reduced[("15/9-F-14", "2009-05-29")] is priority.Priority.MEDIUM
        assert sum(1 for s in scored if s.priority is priority.Priority.HIGH) == 1
        assert not [p for p in reduced.values() if p is priority.Priority.HIGH]


@pytest.mark.skipif(not WORKBOOK.exists(), reason="needs the cached workbook and reports")
class TestTheChartSeriesIsTheDetectorsOwn:
    """`sweep_series` against `sweep_well`, protocol section 21.1.

    The expected rate and its band are not readings: they are the output of the model section 7
    selected, fitted on the window section 7 chose, at the step count the detector used. The console
    must draw the band the verdict was judged against, so the two loops are pinned together here.
    """

    WELLS = ("15/9-F-12", "15/9-F-14")

    def swept(self, well: str) -> tuple[list[Episode], list[SeriesPoint]]:
        history = load_volve_production(WORKBOOK)
        split = derive_split(history.days)
        days = development_only(history.for_well(well), split)
        windows = stable_reference_windows(
            days, activity_dates=activity_dates_by_well(REPORTS).get(well, set())
        )
        model = NaiveMedian28()
        return sweep_well(well, days, windows, model), sweep_series(well, days, windows, model)

    def valid_window(self, episode: Episode, points: list[SeriesPoint]) -> list[SeriesPoint]:
        return [
            p
            for p in points
            if episode.onset <= p.date <= episode.offset
            and p.day_class is DayClass.VALID_PRODUCING
        ]

    def test_every_onset_and_trigger_run_is_below_band_in_the_series(self) -> None:
        for well in self.WELLS:
            episodes, points = self.swept(well)
            by_date = {p.date: p for p in points}
            assert episodes, well
            for episode in episodes:
                assert by_date[episode.onset].below_band, (well, episode.onset)
                run = self.valid_window(episode, points)[:MIN_TRIGGER_RUN]
                assert len(run) == MIN_TRIGGER_RUN, (well, episode.onset)
                assert all(p.below_band for p in run), (well, episode.onset)

    def test_a_window_may_contain_days_back_inside_the_band(self) -> None:
        """Section 9 extends an episode through short recoveries, so this is expected.

        Asserted rather than left implicit, because the obvious stronger property is false: it fails
        on 5 of the 14 development episodes, and a reader who assumed it would mistrust the chart
        whenever a point sat inside the band.
        """
        recovered = 0
        for well in self.WELLS:
            episodes, points = self.swept(well)
            for episode in episodes:
                recovered += sum(1 for p in self.valid_window(episode, points) if not p.below_band)
        assert recovered > 0

    def test_a_day_that_is_not_valid_producing_has_no_derived_figure(self) -> None:
        """The model predicts per valid producing day, so a shut-in day gets no line and no ratio.

        The water cut is here for a reason found by this test. A first version computed it on every
        governed day and published four negative water cuts, down to -2.61, on days the classifier
        had already quarantined with `negative_volume`. A day section 6 refuses is a day nothing may
        be derived from.
        """
        for well in self.WELLS:
            _, points = self.swept(well)
            for point in points:
                if point.day_class is not DayClass.VALID_PRODUCING:
                    assert point.expected is None
                    assert point.lower is None
                    assert point.upper is None
                    assert point.water_cut is None
                    assert not point.below_band

    def test_every_published_water_cut_is_a_fraction(self) -> None:
        published = 0
        for well in self.WELLS:
            _, points = self.swept(well)
            for point in points:
                if point.water_cut is not None:
                    published += 1
                    assert 0.0 <= point.water_cut <= 1.0, (well, point.date, point.water_cut)
        assert published > 1_000


class TestEachConsoleGateCanFail:
    """Section 21.6's eight marks, each shown failing.

    Five phases of this project ended with a gate that could not fail, so a mark without a failing
    case here is not a mark. The inputs are built by hand rather than taken from a run, because a
    gate fed only the artifacts of a passing run is the shape the whole pattern reduces to.
    """

    def sourced(self, value: object = 1, source: str = "investigation.episodes") -> Sourced:
        return Sourced(value=value, source=source)

    def test_a_bare_number_in_a_payload_fails_mark_1(self) -> None:
        outcome = gates.figures_resolve(
            {"made_up": {"shortfall": 12345.0}},
            {"investigation": {"episodes": 14}},
            fact_ids=frozenset(),
            artifacts=Path("/nonexistent"),
        )
        assert not outcome.passed
        assert any("bare number" in line for line in outcome.detail)

    def test_a_source_that_resolves_to_nothing_fails_mark_1(self) -> None:
        outcome = gates.figures_resolve(
            {"made_up": {"figure": self.sourced(source="investigation.no_such_key")}},
            {"investigation": {"episodes": 14}},
            fact_ids=frozenset(),
            artifacts=Path("/nonexistent"),
        )
        assert not outcome.passed
        assert any("resolves to nothing" in line for line in outcome.detail)

    def test_a_table_that_miscounts_its_rows_fails_mark_1(self) -> None:
        """Amendment 10's exemption is bounded by the row count, so a mismatch voids it."""
        series = ChartSeries(
            source="rule:test",
            rows=(),
            row_count=Sourced(value=99, source="rule:test"),
            episode_window="x",
            governing_window="y",
        )
        outcome = gates.figures_resolve(
            {"made_up": series},
            {},
            fact_ids=frozenset(),
            artifacts=Path("/nonexistent"),
        )
        assert not outcome.passed
        assert any("claims 99 rows and carries 0" in line for line in outcome.detail)

    def test_a_mockup_placeholder_in_a_payload_fails_mark_2(self, tmp_path: Path) -> None:
        mockup = tmp_path / "mockup.jsx"
        mockup.write_text('const wape = "11.2%"; const id = "fact_0871";', encoding="utf-8")
        outcome = gates.no_placeholder_appears(
            {"queue": 'the model reached fact_0871 at 11.2%'}, mockup
        )
        assert not outcome.passed
        assert any("fact_0871" in line for line in outcome.detail)

    def test_an_absent_mockup_makes_mark_2_vacuous_rather_than_passing_quietly(
        self, tmp_path: Path
    ) -> None:
        outcome = gates.no_placeholder_appears({"queue": "anything"}, tmp_path / "absent.jsx")
        assert outcome.passed
        assert outcome.vacuous
        assert any("not present" in line for line in outcome.detail)

    @pytest.mark.parametrize("name", ["15/9-F-4", "F-5"])
    def test_a_hold_out_well_in_a_payload_fails_mark_3(self, name: str) -> None:
        outcome = gates.no_hold_out_well({"queue": f"the episode on {name} ran clean"})
        assert not outcome.passed
        assert any(name.split("-", 1)[-1] in line for line in outcome.detail)

    def test_an_abstention_with_an_empty_missing_list_fails_mark_4(self) -> None:
        """The defect this mark found in the real screen, kept as the failing case.

        `15/9-F-14` from 2012-03-11 abstains with every channel available, and the first version of
        the panel showed an empty missing list, which reads as the system saying there was no reason
        it could not conclude.
        """
        outcome = gates.abstention_renders(
            [("x", "insufficient_evidence", EvidenceCoverage(available=("a",), missing=()))]
        )
        assert not outcome.passed
        assert any("nothing listed as missing" in line for line in outcome.detail)

    def test_mark_4_examines_only_the_findings_that_abstained(self) -> None:
        """So it cannot pass by looking at a supported finding instead."""
        outcome = gates.abstention_renders(
            [("x", "supported_explanation", EvidenceCoverage(available=(), missing=()))]
        )
        assert outcome.passed
        assert outcome.vacuous

    def test_a_currency_figure_without_its_assumption_fails_mark_5(self) -> None:
        """`Money` refuses this at construction, so the gate is shown the shape that bypasses it."""
        tile = Money(reason="placeholder").model_copy(
            update={"amount": Sourced(value=1_000_000.0, source="rule:test"), "assumption": None}
        )
        outcome = gates.money_carries_its_assumption([("Estimated cost", tile)])
        assert not outcome.passed
        assert any("no assumption" in line for line in outcome.detail)

    def test_a_non_finite_currency_figure_fails_mark_5(self) -> None:
        """Review fed the post-mortem's currency gate `nan` and it approved it. Not here."""
        tile = Money(
            amount=Sourced(value=float("nan"), source="rule:test"),
            assumption="at a stated rate",
        )
        outcome = gates.money_carries_its_assumption([("Estimated cost", tile)])
        assert not outcome.passed
        assert any("non-finite" in line for line in outcome.detail)

    def test_a_money_tile_with_neither_figure_nor_reason_fails_mark_5(self) -> None:
        tile = Money(reason="placeholder").model_copy(update={"reason": None})
        outcome = gates.money_carries_its_assumption([("Estimated cost", tile)])
        assert not outcome.passed
        assert any("reads as a bug" in line for line in outcome.detail)

    def test_a_log_that_accepts_a_second_judgement_fails_mark_6(self, tmp_path: Path) -> None:
        class Permissive(ReviewLog):
            def append(self, *args: object, **kwargs: object) -> ReviewRecord:
                return ReviewRecord(
                    investigation_id="probe-never-reviewed",
                    action=Action.CONFIRM,
                    actor="permissive",
                    recorded_at="1970-01-01T00:00:00+00:00",
                    investigator_version="investigator-v0",
                    protocol_version="probe",
                )

            def state_of(self, investigation_id: str) -> str:
                return "confirmed"

        outcome = gates.review_log_is_append_only(Permissive(tmp_path / "l.jsonl"))
        assert not outcome.passed
        assert any("settled finding" in line for line in outcome.detail)

    def test_a_log_that_refuses_everything_also_fails_mark_6(self, tmp_path: Path) -> None:
        """The other direction. A log that accepts nothing satisfies every refusal probe."""

        class RefusesEverything(ReviewLog):
            def append(self, *args: object, **kwargs: object) -> ReviewRecord:
                raise ReviewRefused("nothing may ever be recorded")

        outcome = gates.review_log_is_append_only(RefusesEverything(tmp_path / "l.jsonl"))
        assert not outcome.passed
        assert any("accepts nothing" in line for line in outcome.detail)

    def test_a_writing_route_outside_the_review_prefix_fails_mark_7(self) -> None:
        outcome = gates.api_is_read_only(
            [("/api/investigations/{id}", frozenset({"GET", "DELETE"}))]
        )
        assert not outcome.passed
        assert any("DELETE" in line for line in outcome.detail)

    def test_a_review_route_may_write(self) -> None:
        outcome = gates.api_is_read_only([("/api/review/{id}/confirm", frozenset({"POST"}))])
        assert outcome.passed

    def test_a_priority_score_that_disagrees_with_the_rule_fails_mark_8(self) -> None:
        outcome = gates.priority_matches_the_printed_rule(
            [("x", 99, 1_000.0, 5, "supported_explanation", "high", "none")],
            ("30,000", "10,000", "40", "5"),
        )
        assert not outcome.passed
        assert any("the rule gives 1 and the payload says 99" in line for line in outcome.detail)

    def test_a_printed_rule_missing_a_threshold_fails_mark_8(self) -> None:
        """The rule has to state its own numbers, or a reader cannot recompute a score from it."""
        outcome = gates.priority_matches_the_printed_rule([], ("30,000", "10,000"))
        assert not outcome.passed
        assert any("does not state the threshold 40" in line for line in outcome.detail)


@pytest.mark.skipif(not MANIFEST.exists(), reason="needs cached runs")
class TestTheConsoleGatesOnTheRealRun:
    """Every mark against the payloads the API actually serves."""

    def test_all_eight_marks_pass_and_none_is_vacuous(self) -> None:
        from volve_ops.console.store import DEFAULT_TRACES, RunStore

        store = RunStore()
        manifests = store.manifests()
        queue = assemble.queue(store)
        details = {
            r.investigation_id: assemble.detail(store, r.investigation_id) for r in queue.rows
        }
        payloads: dict[str, BaseModel] = {
            "queue": queue,
            "header": assemble.header(store),
            **details,
        }
        fact_ids: frozenset[str] = frozenset()
        for detail in details.values():
            fact_ids |= store.resolvable_ids(detail.well, detail.period.split(" to ")[0])
        rendered = {name: payload.model_dump_json() for name, payload in payloads.items()}

        resolved = gates.figures_resolve(
            payloads, manifests, fact_ids=fact_ids, artifacts=DEFAULT_TRACES
        )
        assert resolved.passed, resolved.detail
        assert resolved.examined > 200

        held = gates.no_hold_out_well(rendered)
        assert held.passed, held.detail

        abstentions = gates.abstention_renders(
            [(r.investigation_id, r.assessment, details[r.investigation_id].coverage)
             for r in queue.rows]
        )
        assert abstentions.passed, abstentions.detail
        assert abstentions.examined == 4

        money = gates.money_carries_its_assumption(
            [(t.label, t.money) for t in queue.kpis if t.money is not None]
        )
        assert money.passed, money.detail

    def test_no_engineering_vocabulary_reaches_an_operator_screen(self) -> None:
        """Decision 5, measured. Reported by the harness rather than gated, per section 21.6."""
        from volve_ops.console.store import RunStore

        store = RunStore()
        queue = assemble.queue(store)
        rendered = {
            r.investigation_id: assemble.detail(store, r.investigation_id).model_dump_json()
            for r in queue.rows
        }
        rendered["queue"] = queue.model_dump_json()
        assert gates.operator_screens_avoid_engineering_words(rendered) == []
