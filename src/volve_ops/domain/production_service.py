"""The production pipeline, assembled once so every caller gets the same sequence.

Reading, duplicate collapsing and classification are separate functions because they are
separately testable, but they have to happen in that order with the right flags, and a caller
that assembles them by hand will eventually assemble them differently. Published figures come
from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass, classify
from volve_ops.ingest.production import CapacityLimits, DuplicateConflict, collapse_duplicates
from volve_ops.ingest.production_reader import read_daily_production

# The Volve workbook carries a flow-kind column and gas and water volumes. Both facts are
# properties of this source, so they are stated here rather than guessed at in the classifier.
VOLVE_HAS_STATUS_COLUMN = True
VOLVE_HAS_GAS_AND_WATER_COLUMNS = True


class ProductionHistory(BaseModel):
    """Every well-day from one source, classified, with what was set aside and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    days: tuple[ClassifiedDay, ...]
    duplicate_conflicts: tuple[DuplicateConflict, ...]

    def of_class(self, day_class: DayClass) -> tuple[ClassifiedDay, ...]:
        return tuple(d for d in self.days if d.day_class is day_class)

    def for_well(self, well: str) -> tuple[ClassifiedDay, ...]:
        return tuple(d for d in self.days if d.day.well == well)

    @property
    def wells(self) -> tuple[str, ...]:
        return tuple(sorted({d.day.well for d in self.days}))

    def class_counts(self) -> dict[DayClass, int]:
        counts: dict[DayClass, int] = {c: 0 for c in DayClass}
        for d in self.days:
            counts[d.day_class] += 1
        return counts


def load_volve_production(
    path: Path, *, capacity: CapacityLimits | None = None
) -> ProductionHistory:
    """Read the Volve workbook into classified days.

    Duplicates are collapsed before classification, because the one-class-per-well-day
    guarantee the protocol rests on is only true once a well-day is a single row. Conflicting
    duplicates are returned rather than dropped.
    """
    rows = list(read_daily_production(path))
    kept, conflicts = collapse_duplicates(rows)
    classified: Sequence[ClassifiedDay] = [
        classify(
            row,
            capacity=capacity,
            gas_and_water_columns_present=VOLVE_HAS_GAS_AND_WATER_COLUMNS,
            status_column_present=VOLVE_HAS_STATUS_COLUMN,
        )
        for row in kept
    ]
    return ProductionHistory(days=tuple(classified), duplicate_conflicts=tuple(conflicts))
