"""Lexical retrieval over the narrative text of drilling reports.

docs/eval_protocol.md section 15 fixes `bm25-only` as the baseline a hybrid approach has to
beat, so this is both that baseline and the lexical half of whatever eventually replaces it.

Implemented here rather than pulled in, for two reasons. The corpus is small enough that a
dependency buys nothing, and the scoring has to be inspectable: when a conclusion rests on a
retrieved document, the reason it ranked where it did should be readable rather than held in a
library's internals.

Only narrative goes in. Structured data is queried through typed tools and is never indexed,
because similarity over numbers retrieves the wrong well and the wrong month and gives no way
to tell that it has.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from volve_ops.extraction.npt import NPTEvent

# Okapi BM25's usual parameters: k1 controls how fast term frequency saturates, b how strongly
# length is normalised. The standard defaults, chosen because they are standard. A tuned pair
# on a corpus this size would be fitted to it, and the baseline is meant to be a fixed opponent.
K1: Final[float] = 1.5
B: Final[float] = 0.75

_TOKEN = re.compile(r"[a-z0-9][a-z0-9/'\-]*")


def tokenise(text: str) -> list[str]:
    """Lowercase word tokens, keeping the slashes and hyphens well names depend on.

    `15/9-F-12` has to survive as something searchable. A tokeniser that splits on every
    non-letter turns it into four meaningless numbers.
    """
    return _TOKEN.findall(text.lower())


class Chunk(BaseModel):
    """One retrievable unit of narrative, with the metadata a filter needs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str
    text: str
    well: str
    wellbore: str
    source_document: str
    report_date: str
    activity_code: str = ""


class ScoredChunk(BaseModel):
    """A retrieval hit, with the terms that earned it its score."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk: Chunk
    score: float
    matched_terms: tuple[str, ...]


class BM25Index:
    """A lexical index over narrative chunks.

    Scoring is exposed term by term so a result can be explained. A hit whose score came
    entirely from one common word is different evidence from one that matched the query's rare
    terms, and an investigation that cannot tell them apart will treat them the same.
    """

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self.chunks: list[Chunk] = list(chunks)
        self._tokens: list[list[str]] = [tokenise(c.text) for c in self.chunks]
        self._lengths: list[int] = [len(t) for t in self._tokens]
        self._average_length: float = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )
        self._frequencies: list[Counter[str]] = [Counter(t) for t in self._tokens]
        self._postings: dict[str, list[int]] = defaultdict(list)
        for position, counts in enumerate(self._frequencies):
            for term in counts:
                self._postings[term].append(position)

    def __len__(self) -> int:
        return len(self.chunks)

    def idf(self, term: str) -> float:
        """Inverse document frequency. Zero for a term the corpus does not contain."""
        documents = len(self.chunks)
        containing = len(self._postings.get(term, ()))
        if containing == 0:
            return 0.0
        return math.log(1.0 + (documents - containing + 0.5) / (containing + 0.5))

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        well: str | None = None,
        wellbore: str | None = None,
        on_or_after: str | None = None,
        on_or_before: str | None = None,
    ) -> list[ScoredChunk]:
        """Rank chunks against a query, optionally filtered to a well, wellbore or date range.

        Every filter applies before scoring, not after. Filtering a ranked list spends the budget
        on results that are then discarded: ask for five and get two, because three belonged to
        another well. The date range exists for the same reason and was added once an investigation
        asked for three hits near an episode and got none, because the well's three best matches
        were years away from it.

        Dates are ISO strings compared lexically, which is exactly right for `YYYY-MM-DD` and is
        how the chunks already store them.
        """
        terms = tokenise(query)
        if not terms:
            return []

        candidates: set[int] = set()
        for term in terms:
            candidates.update(self._postings.get(term, ()))

        scored: list[ScoredChunk] = []
        # Sorted, not a set. Float addition is not associative, so iterating a set made each
        # score depend on the hash seed: the same query gave 10.655254513445765 under one seed
        # and ...63 under another, and the chunk_id tiebreak only fires on exact equality, so a
        # genuine tie could be broken differently between runs.
        unique_terms = sorted(set(terms))
        for position in candidates:
            chunk = self.chunks[position]
            if well is not None and chunk.well != well:
                continue
            if wellbore is not None and chunk.wellbore != wellbore:
                continue
            if on_or_after is not None and chunk.report_date < on_or_after:
                continue
            if on_or_before is not None and chunk.report_date > on_or_before:
                continue

            counts = self._frequencies[position]
            length = self._lengths[position] or 1
            total = 0.0
            matched: list[str] = []
            for term in unique_terms:
                frequency = counts.get(term, 0)
                if frequency == 0:
                    continue
                matched.append(term)
                denominator = frequency + K1 * (
                    1.0 - B + B * length / (self._average_length or 1.0)
                )
                total += self.idf(term) * frequency * (K1 + 1.0) / denominator
            if total > 0.0:
                scored.append(
                    ScoredChunk(chunk=chunk, score=total, matched_terms=tuple(sorted(matched)))
                )

        scored.sort(key=lambda s: (-s.score, s.chunk.chunk_id))
        return scored[:limit]


def chunks_from_events(events: Sequence[NPTEvent]) -> list[Chunk]:
    """Build retrievable chunks from extracted NPT events.

    One chunk per event comment. The drilling reports' narrative is already written in short
    units, each tied to a timestamp and an activity, so splitting or merging them would discard
    the alignment that makes a retrieved span citable back to the event it describes.
    """
    return [
        Chunk(
            chunk_id=event.event_id,
            text=event.comment,
            well=event.well,
            wellbore=event.wellbore,
            source_document=event.source_document,
            report_date=str(event.report_date),
            activity_code=event.activity_code,
        )
        for event in events
        if event.comment.strip()
    ]
