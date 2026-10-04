"""Candidate expectation models and the fitted expectation they produce.

The expectation is what every investigation is measured against, so it is evaluated on its own
before any agent reasoning is built on it. A bad expectation does not produce bad explanations;
it produces investigations into episodes that never happened.

Every model here is fitted on a stable reference window and then carried forward without
refitting, which is how the detector actually uses it: an expectation is established from a
period when the well was behaving, then held across the period in question. Evaluating a model
by refitting it each day would measure something the system never does.

Models are deliberately simple and interpretable. A decline curve can be read off a chart and
argued with; a gradient-boosted ensemble cannot, and an operator being asked to accept that a
well underperformed deserves to see why the expectation was what it was.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict

from volve_ops.domain.day_class import ClassifiedDay, DayClass

# docs/eval_protocol.md section 3 fixes both naive baselines and exempts them from amendment.
NAIVE_MEDIAN_WINDOW_DAYS = 28
LOWER_QUANTILE = 0.10
UPPER_QUANTILE = 0.90


class Prediction(BaseModel):
    """A point expectation with the interval the detector compares against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    q_expected: float
    lower: float
    upper: float


def _rates(days: Sequence[ClassifiedDay]) -> list[float]:
    """Normalised rates of the valid producing days, in order."""
    out = []
    for d in days:
        if d.day_class is DayClass.VALID_PRODUCING:
            rate = d.q_24h
            if rate is not None:
                out.append(rate)
    return out


def _empirical_quantile(values: Sequence[float], q: float) -> float:
    """Nearest-rank quantile. No interpolation, so the bound is an observed value."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


class FittedExpectation(BaseModel):
    """A model fitted to one window, able to predict forward without refitting."""

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    model_name: str
    q_at_fit: float
    decline_rate: float = 0.0
    hyperbolic_b: float = 0.0
    lower_offset: float = 0.0
    upper_offset: float = 0.0
    rate_per_choke: float | None = None
    widen_with_horizon: bool = True

    def predict(self, steps_ahead: int, *, choke: float | None = None) -> Prediction:
        """Expectation `steps_ahead` valid producing days after the end of the fit window.

        For candidate models the interval widens as the square root of the horizon. The offsets
        come from one-step residuals inside the window, and carrying them forward unchanged
        would claim that a prediction four weeks out is as certain as one made the next day.
        Under independent increments the error of a carried-forward level grows as the square
        root of the number of steps, which is the simplest growth law that is not obviously
        wrong, and it is stated here rather than tuned to make coverage come out right.

        The two naive baselines are excluded from that, with `widen_with_horizon` false. Their
        interval is fixed by docs/eval_protocol.md section 3 as the empirical 10th and 90th
        percentile of rate over the trailing 28 valid producing days, and section 13 exempts
        both baselines from amendment. Widening their band would be an amendment to something
        the protocol says cannot be amended, and since the selected expectation is one of them,
        it would also change the published episodes.
        """
        t = float(steps_ahead)
        if self.rate_per_choke is not None and choke is not None:
            q = self.rate_per_choke * choke
        elif self.hyperbolic_b > 0.0:
            denominator = 1.0 + self.hyperbolic_b * self.decline_rate * t
            q = self.q_at_fit / max(denominator, 1e-9) ** (1.0 / self.hyperbolic_b)
        elif self.decline_rate != 0.0:
            q = self.q_at_fit * math.exp(-self.decline_rate * t)
        else:
            q = self.q_at_fit
        q = max(q, 0.0)
        spread = math.sqrt(max(t, 1.0)) if self.widen_with_horizon else 1.0
        return Prediction(
            q_expected=q,
            lower=max(q + self.lower_offset * spread, 0.0),
            upper=max(q + self.upper_offset * spread, q),
        )


class ExpectationModel(ABC):
    """A candidate expectation. Fitted on a window, then carried forward."""

    name: str

    @abstractmethod
    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        """Fit, or return None if the window cannot support this model."""


class NaiveMedian28(ExpectationModel):
    """The robust median of the last 28 valid producing days, carried forward.

    Fixed by docs/eval_protocol.md section 3 and exempt from amendment: a pass mark expressed
    relative to a baseline means nothing if the baseline can move.
    """

    name = "naive-median28"

    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        rates = _rates(window)[-NAIVE_MEDIAN_WINDOW_DAYS:]
        if not rates:
            return None
        centre = median(rates)
        return FittedExpectation(
            model_name=self.name,
            q_at_fit=centre,
            lower_offset=_empirical_quantile(rates, LOWER_QUANTILE) - centre,
            upper_offset=_empirical_quantile(rates, UPPER_QUANTILE) - centre,
            widen_with_horizon=False,
        )


class NaivePersistence(ExpectationModel):
    """The most recent valid producing day's rate, carried forward.

    A comparator only. Section 8 bars it from being the fallback expectation, because after one
    day of reduced rate the reduced rate becomes the expectation and sustained underperformance
    stops being detectable by construction.
    """

    name = "naive-persistence"

    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        rates = _rates(window)
        if not rates:
            return None
        trailing = rates[-NAIVE_MEDIAN_WINDOW_DAYS:]
        last = rates[-1]
        # Section 3 fixes the band at the trailing percentiles themselves, not at an offset
        # from the point forecast. Re-centring on the last rate would shift the whole band by
        # however far that day sat from the window median, which is a different interval from
        # the one the protocol names.
        return FittedExpectation(
            model_name=self.name,
            q_at_fit=last,
            lower_offset=_empirical_quantile(trailing, LOWER_QUANTILE) - last,
            upper_offset=_empirical_quantile(trailing, UPPER_QUANTILE) - last,
            widen_with_horizon=False,
        )


def _fit_residual_offsets(rates: Sequence[float], fitted: Sequence[float]) -> tuple[float, float]:
    """Interval offsets from the in-window residuals of a fitted curve."""
    residuals = [a - f for a, f in zip(rates, fitted, strict=True)]
    return (
        _empirical_quantile(residuals, LOWER_QUANTILE),
        _empirical_quantile(residuals, UPPER_QUANTILE),
    )


class ExponentialDecline(ExpectationModel):
    """Arps exponential decline, fitted by least squares on log rate.

    The standard first description of a producing well: output falls by a constant proportion
    per unit time. Fitted only within a window, never across one, because a decline fitted
    through an intervention describes neither side of it.
    """

    name = "exponential-decline"

    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        rates = _rates(window)
        positive = [(i, r) for i, r in enumerate(rates) if r > 0.0]
        if len(positive) < 5:
            return None

        n = len(positive)
        mean_t = sum(i for i, _ in positive) / n
        mean_y = sum(math.log(r) for _, r in positive) / n
        numerator = sum((i - mean_t) * (math.log(r) - mean_y) for i, r in positive)
        denominator = sum((i - mean_t) ** 2 for i, _ in positive)
        if denominator == 0.0:
            return None

        slope = numerator / denominator
        intercept = mean_y - slope * mean_t
        last_t = len(rates) - 1
        q_end = math.exp(intercept + slope * last_t)

        fitted = [math.exp(intercept + slope * i) for i in range(len(rates))]
        lower, upper = _fit_residual_offsets(rates, fitted)
        # A positive slope is production rising, which decline curves do not describe; carry
        # the level forward rather than extrapolating growth.
        return FittedExpectation(
            model_name=self.name,
            q_at_fit=q_end,
            decline_rate=max(-slope, 0.0),
            lower_offset=lower,
            upper_offset=upper,
        )


class HyperbolicDecline(ExpectationModel):
    """Arps hyperbolic decline with the curvature fixed rather than fitted.

    b is held at 0.5, in the middle of the range usually seen for solution-gas and water-drive
    reservoirs. Fitting b as well on windows of a few dozen days produces unstable exponents
    that extrapolate wildly, which is a worse failure than a slightly wrong curvature.
    """

    name = "hyperbolic-decline"
    b = 0.5

    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        exponential = ExponentialDecline().fit(window)
        if exponential is None:
            return None
        rates = _rates(window)
        d = exponential.decline_rate
        if d <= 0.0:
            return FittedExpectation(
                model_name=self.name,
                q_at_fit=exponential.q_at_fit,
                lower_offset=exponential.lower_offset,
                upper_offset=exponential.upper_offset,
            )

        # Evaluating the curve backwards from the window's end drives the base non-positive
        # once the window is longer than 2/(b*d). Clamping it, as an earlier version did, turns
        # a domain error into a fitted value around 1e19, which produces a lower offset so
        # negative that the band's lower edge is pinned at zero and the model records no
        # exceedances by construction. Refusing to fit is the honest outcome: this curvature
        # cannot describe this window.
        start = len(rates) - 1
        bases = [1.0 + self.b * d * (i - start) for i in range(len(rates))]
        if min(bases) <= 0.0:
            return None

        fitted = [exponential.q_at_fit / base ** (1.0 / self.b) for base in bases]
        lower, upper = _fit_residual_offsets(rates, fitted)
        return FittedExpectation(
            model_name=self.name,
            q_at_fit=exponential.q_at_fit,
            decline_rate=d,
            hyperbolic_b=self.b,
            lower_offset=lower,
            upper_offset=upper,
        )


class ChokeScaledBaseline(ExpectationModel):
    """An operating-condition-aware baseline: rate in proportion to choke opening.

    The other candidates answer "what should this well produce, given how long it has been
    producing". This one answers a different and more useful question: "given that the well was
    choked back to 40 percent today, what should it produce today". A choke reduction then stops
    looking like underperformance, which is the single most common way a naive expectation
    manufactures an episode.

    That is also its limit, and the reason it cannot be the whole answer. A choke is often
    reduced *because* of a problem, so an expectation that follows the choke will quietly
    absorb the consequences of the very thing an investigation is trying to find. It belongs in
    the comparison as a second opinion, not as the primary expectation.
    """

    name = "choke-scaled"

    def fit(self, window: Sequence[ClassifiedDay]) -> FittedExpectation | None:
        pairs = [
            (d.day.choke_size, d.q_24h)
            for d in window
            if d.day_class is DayClass.VALID_PRODUCING
            and d.day.choke_size is not None
            and d.day.choke_size > 0.0
            and d.q_24h is not None
        ]
        if len(pairs) < 5:
            return None
        ratios = [rate / choke for choke, rate in pairs]
        centre = median(ratios)
        rates = [r for _, r in pairs]
        level = median(rates)
        return FittedExpectation(
            model_name=self.name,
            q_at_fit=level,
            rate_per_choke=centre,
            lower_offset=_empirical_quantile(rates, LOWER_QUANTILE) - level,
            upper_offset=_empirical_quantile(rates, UPPER_QUANTILE) - level,
        )


CANDIDATE_MODELS: tuple[ExpectationModel, ...] = (
    NaiveMedian28(),
    NaivePersistence(),
    ExponentialDecline(),
    HyperbolicDecline(),
    ChokeScaledBaseline(),
)
