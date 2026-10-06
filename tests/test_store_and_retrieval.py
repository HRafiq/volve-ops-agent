"""The versioned event store and the lexical index."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from volve_ops.extraction.npt import NPTEvent
from volve_ops.extraction.store import EventStore, content_hash
from volve_ops.retrieval.index import BM25Index, Chunk, chunks_from_events, tokenise


def event(
    event_id: str = "npt_0001",
    well: str = "15/9-F-12",
    comment: str = "Mud pump 1 failed, changed liners.",
    code: str = "interruption -- repair",
) -> NPTEvent:
    return NPTEvent(
        event_id=event_id,
        well=well,
        wellbore=well,
        source_document="d.xml",
        report_date=dt.date(2010, 6, 1),
        start_time=dt.datetime(2010, 6, 1, 4),
        end_time=dt.datetime(2010, 6, 1, 6),
        duration_hours=2.0,
        activity_code=code,
        category=code.split("--")[0].strip(),
        subcategory=code.split("--")[1].strip(),
        state="fail",
        state_detail="equipment failure",
        comment=comment,
    )


class TestEventStore:
    def test_a_version_round_trips(self, tmp_path: Path) -> None:
        store = EventStore(tmp_path)
        events = [event("npt_1"), event("npt_2", comment="Waiting on weather.")]
        manifest = store.write(events, version="v0", source_directory=tmp_path, source_file_count=2)
        assert manifest.event_count == 2
        assert [e.event_id for e in store.read("v0")] == ["npt_1", "npt_2"]
        assert store.versions() == ["v0"]

    def test_overwriting_a_version_is_refused(self, tmp_path: Path) -> None:
        """A version rewritten in place makes every result traced to it a guess."""
        store = EventStore(tmp_path)
        store.write([event()], version="v0", source_directory=tmp_path, source_file_count=1)
        with pytest.raises(FileExistsError, match="already exists"):
            store.write([event()], version="v0", source_directory=tmp_path, source_file_count=1)

    def test_versions_coexist(self, tmp_path: Path) -> None:
        store = EventStore(tmp_path)
        store.write([event()], version="v0", source_directory=tmp_path, source_file_count=1)
        store.write(
            [event(), event("npt_2")], version="v1", source_directory=tmp_path, source_file_count=1
        )
        assert store.versions() == ["v0", "v1"]
        assert store.manifest("v0").event_count == 1
        assert store.manifest("v1").event_count == 2

    def test_the_content_hash_ignores_write_order(self) -> None:
        """A digest that changes when nothing of substance did trains the reader to ignore it."""
        a, b = event("npt_1"), event("npt_2")
        assert content_hash([a, b]) == content_hash([b, a])

    def test_the_content_hash_notices_a_changed_value(self) -> None:
        assert content_hash([event()]) != content_hash([event(comment="something else")])

    def test_verify_catches_a_tampered_store(self, tmp_path: Path) -> None:
        store = EventStore(tmp_path)
        store.write([event()], version="v0", source_directory=tmp_path, source_file_count=1)
        store.verify("v0")

        path = tmp_path / "v0" / "events.jsonl"
        path.write_text(path.read_text().replace("Mud pump 1", "Mud pump 2"), encoding="utf-8")
        with pytest.raises(ValueError, match="does not match its manifest"):
            store.verify("v0")

    def test_reading_an_unknown_version_is_an_error(self, tmp_path: Path) -> None:
        store = EventStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            list(store.read("nope"))
        with pytest.raises(FileNotFoundError):
            store.manifest("nope")


class TestTokenisation:
    def test_well_names_survive(self) -> None:
        """Splitting on every non-letter turns 15/9-F-12 into four meaningless numbers."""
        assert "15/9-f-12" in tokenise("Problem on 15/9-F-12 today")

    def test_case_is_folded(self) -> None:
        assert tokenise("MUD PUMP") == tokenise("mud pump")

    def test_punctuation_does_not_become_a_term(self) -> None:
        assert tokenise("Failed. Again!") == ["failed", "again"]


class TestBM25Index:
    @staticmethod
    def _index() -> BM25Index:
        return BM25Index(
            chunks_from_events(
                [
                    event("a", comment="Mud pump 1 failed, washout in valve seat."),
                    event("b", comment="Waiting on weather, sea state too high."),
                    event("c", well="15/9-F-14", comment="Stuck pipe, jarred free after 3 hours."),
                    event("d", well="15/9-F-14", comment="Mud pump maintenance, routine."),
                ]
            )
        )

    def test_a_query_finds_the_relevant_chunk_first(self) -> None:
        hits = self._index().search("stuck pipe", limit=2)
        assert hits[0].chunk.chunk_id == "c"

    def test_the_matched_terms_explain_the_score(self) -> None:
        """A hit scored entirely by one common word is different evidence from a rare match."""
        (hit,) = self._index().search("washout", limit=1)
        assert hit.matched_terms == ("washout",)
        assert hit.score > 0

    def test_filtering_happens_before_ranking(self) -> None:
        """Filtering a ranked list spends the budget on results that are then discarded."""
        hits = self._index().search("mud pump", limit=2, well="15/9-F-14")
        assert {h.chunk.well for h in hits} == {"15/9-F-14"}
        assert len(hits) == 1

    def test_a_term_the_corpus_lacks_scores_nothing(self) -> None:
        assert self._index().search("helicopter") == []

    def test_an_empty_query_returns_nothing_rather_than_everything(self) -> None:
        assert self._index().search("   ") == []

    def test_rarer_terms_carry_more_weight(self) -> None:
        index = self._index()
        assert index.idf("washout") > index.idf("mud")

    def test_ranking_is_deterministic_on_ties(self) -> None:
        index = self._index()
        assert [h.chunk.chunk_id for h in index.search("mud pump", limit=4)] == [
            h.chunk.chunk_id for h in index.search("mud pump", limit=4)
        ]

    def test_events_without_a_comment_are_not_indexed(self) -> None:
        chunks = chunks_from_events([event("a"), event("b", comment="   ")])
        assert [c.chunk_id for c in chunks] == ["a"]

    def test_a_chunk_keeps_the_metadata_a_citation_needs(self) -> None:
        (chunk,) = chunks_from_events([event()])
        assert isinstance(chunk, Chunk)
        assert chunk.source_document == "d.xml"
        assert chunk.report_date == "2010-06-01"
        assert chunk.activity_code == "interruption -- repair"
