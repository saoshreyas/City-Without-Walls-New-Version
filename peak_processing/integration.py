"""Guide-driven integration of unintegrated chromatogram peaks."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from .guide import CategorySet, PeakGuideEntry, normalize_compound_name, require_guide_entry


@dataclass(frozen=True)
class SamplePoint:
    """One unintegrated chromatogram point."""

    retention_time_min: float
    intensity: float


@dataclass(frozen=True)
class ManualArea:
    """Manual/correct integration values for comparison."""

    sample_id: str
    compound: str
    area: float
    start_rt_min: float | None = None
    end_rt_min: float | None = None


@dataclass
class IntegrationResult:
    """The selected integration algorithm and calculated peak area."""

    sample_id: str
    compound: str
    integrated: bool
    action: str
    guide_before: CategorySet
    guide_after: CategorySet
    observed_before: CategorySet
    algorithm_steps: list[str] = field(default_factory=list)
    start_rt_min: float | None = None
    apex_rt_min: float | None = None
    end_rt_min: float | None = None
    area: float | None = None
    raw_area: float | None = None
    peak_height: float | None = None
    manual_area: float | None = None
    area_error: float | None = None
    relative_area_error: float | None = None

    def to_row(self) -> dict[str, str | float | None]:
        return {
            "sample_id": self.sample_id,
            "compound": self.compound,
            "integrated": "yes" if self.integrated else "no",
            "action": self.action,
            "observed_peak_shape": self.observed_before.peak_shape,
            "observed_baseline": self.observed_before.baseline,
            "observed_interference": self.observed_before.interference,
            "observed_retention_shift": self.observed_before.retention_shift,
            "observed_qc_action": self.observed_before.qc_action,
            "guide_before": self.guide_before.summary(),
            "guide_after": self.guide_after.summary(),
            "start_rt_min": self.start_rt_min,
            "apex_rt_min": self.apex_rt_min,
            "end_rt_min": self.end_rt_min,
            "area": self.area,
            "raw_area": self.raw_area,
            "peak_height": self.peak_height,
            "manual_area": self.manual_area,
            "area_error": self.area_error,
            "relative_area_error": self.relative_area_error,
            "algorithm": " ; ".join(self.algorithm_steps),
        }


class PeakIntegrator:
    """Integrate unprocessed peak samples using a loaded processing guide."""

    def __init__(self, guide: dict[str, PeakGuideEntry]):
        self.guide = guide

    def integrate(
        self,
        sample_id: str,
        compound: str,
        points: Sequence[SamplePoint],
    ) -> IntegrationResult:
        entry = require_guide_entry(self.guide, compound)
        ordered = sorted(points, key=lambda point: point.retention_time_min)
        if len(ordered) < 3:
            return self._no_integration_result(
                sample_id,
                entry,
                "Reject: fewer than three data points were supplied.",
            )

        window_points = self._window_points(ordered, entry)
        if len(window_points) < 3:
            return self._no_integration_result(
                sample_id,
                entry,
                "Reject: no data points were found inside the guide RT window.",
            )

        rt = [point.retention_time_min for point in window_points]
        intensities = [point.intensity for point in window_points]
        smoothed = gaussian_smooth(
            intensities,
            entry.gaussian_smooth_width_points if entry.gaussian_smooth_width_points is not None else 1.7,
        )
        baseline = estimate_linear_baseline(rt, smoothed, entry.baseline_sub_window_min)
        corrected = [max(0.0, signal - base) for signal, base in zip(smoothed, baseline)]
        raw_baseline_corrected = [max(0.0, signal - base) for signal, base in zip(intensities, baseline)]
        noise = estimate_noise(corrected, entry.baseline_sub_window_min, rt)
        candidates = find_candidate_apices(
            corrected,
            min_height=entry.min_peak_height or 0.0,
            noise=noise,
            min_separation_points=entry.peak_splitting_points or 1,
        )

        observed = classify_peak(
            entry=entry,
            rt=rt,
            corrected=corrected,
            candidates=candidates,
            noise=noise,
        )
        steps = [
            f"Load guide row for {entry.compound}.",
            f"Smooth with Gaussian width {entry.gaussian_smooth_width_points or 1.7:g} points.",
            self._window_step(entry, rt),
            f"Subtract linear baseline estimated from edge windows ({entry.baseline_sub_window_min or 0:g} min).",
            f"Observed before-integration categories: {observed.summary() or 'uncategorized'}.",
            f"Guide target after-integration categories: {entry.after.summary() or 'none provided'}.",
        ]

        if entry.should_reject:
            steps.append("Guide notes/action request no integration for this compound.")
            return IntegrationResult(
                sample_id=sample_id,
                compound=entry.compound,
                integrated=False,
                action="Reject",
                guide_before=entry.before,
                guide_after=entry.after,
                observed_before=observed,
                algorithm_steps=steps,
            )

        if not candidates:
            steps.append("No candidate apex exceeded the minimum height/noise threshold.")
            return IntegrationResult(
                sample_id=sample_id,
                compound=entry.compound,
                integrated=False,
                action="Reject",
                guide_before=entry.before,
                guide_after=entry.after,
                observed_before=observed,
                algorithm_steps=steps,
            )

        apex_index = select_apex_index(entry, rt, candidates)
        left_index, right_index = find_integration_bounds(
            entry=entry,
            corrected=corrected,
            apex_index=apex_index,
            candidates=candidates,
            noise=noise,
        )
        if left_index == right_index:
            return self._no_integration_result(
                sample_id,
                entry,
                "Reject: integration bounds collapsed to a single point.",
                observed=observed,
                algorithm_steps=steps,
            )

        start_rt = rt[left_index]
        apex_rt = rt[apex_index]
        end_rt = rt[right_index]
        area = trapezoid_area(rt[left_index : right_index + 1], corrected[left_index : right_index + 1])
        raw_area = trapezoid_area(
            rt[left_index : right_index + 1],
            raw_baseline_corrected[left_index : right_index + 1],
        )
        height = corrected[apex_index]
        preference = entry.target_peak_preference
        steps.extend(
            [
                f"Select {preference} candidate apex at {apex_rt:.4g} min.",
                (
                    f"Set integration bounds to {start_rt:.4g}-{end_rt:.4g} min "
                    "using threshold crossing and valley cuts for neighboring peaks."
                ),
                "Integrate baseline-corrected intensity with the trapezoidal rule.",
            ]
        )
        return IntegrationResult(
            sample_id=sample_id,
            compound=entry.compound,
            integrated=True,
            action=entry.after.qc_action or "Accept",
            guide_before=entry.before,
            guide_after=entry.after,
            observed_before=observed,
            algorithm_steps=steps,
            start_rt_min=start_rt,
            apex_rt_min=apex_rt,
            end_rt_min=end_rt,
            area=area,
            raw_area=raw_area,
            peak_height=height,
        )

    def integrate_many(
        self,
        samples: dict[tuple[str, str], list[SamplePoint]],
    ) -> list[IntegrationResult]:
        results = []
        for (sample_id, compound), points in sorted(samples.items()):
            results.append(self.integrate(sample_id, compound, points))
        return results

    def _window_points(
        self,
        points: Sequence[SamplePoint],
        entry: PeakGuideEntry,
    ) -> list[SamplePoint]:
        expected = entry.expected_rt_min
        if expected is None:
            return list(points)
        half_width = (entry.rt_half_window_sec or 30.0) / 60.0
        start = expected - half_width
        end = expected + half_width
        return [point for point in points if start <= point.retention_time_min <= end]

    def _window_step(self, entry: PeakGuideEntry, rt: Sequence[float]) -> str:
        if entry.expected_rt_min is None:
            return "Use all points because the guide has no expected RT."
        half_width = (entry.rt_half_window_sec or 30.0) / 60.0
        return (
            f"Restrict to expected RT {entry.expected_rt_min:g} +/- "
            f"{half_width:g} min ({rt[0]:.4g}-{rt[-1]:.4g} min in sample)."
        )

    def _no_integration_result(
        self,
        sample_id: str,
        entry: PeakGuideEntry,
        reason: str,
        *,
        observed: CategorySet | None = None,
        algorithm_steps: list[str] | None = None,
    ) -> IntegrationResult:
        steps = list(algorithm_steps or [])
        steps.append(reason)
        return IntegrationResult(
            sample_id=sample_id,
            compound=entry.compound,
            integrated=False,
            action="Reject",
            guide_before=entry.before,
            guide_after=entry.after,
            observed_before=observed or CategorySet(qc_action="Reject"),
            algorithm_steps=steps,
        )


def gaussian_smooth(values: Sequence[float], width_points: float) -> list[float]:
    """Apply a small Gaussian smoothing kernel using only the standard library."""

    if not values:
        return []
    sigma = max(float(width_points), 0.01)
    radius = max(1, int(math.ceil(3.0 * sigma)))
    kernel = [math.exp(-0.5 * (offset / sigma) ** 2) for offset in range(-radius, radius + 1)]
    scale = sum(kernel)
    kernel = [weight / scale for weight in kernel]
    smoothed: list[float] = []
    for index in range(len(values)):
        total = 0.0
        used_weight = 0.0
        for offset, weight in zip(range(-radius, radius + 1), kernel):
            source_index = index + offset
            if 0 <= source_index < len(values):
                total += values[source_index] * weight
                used_weight += weight
        smoothed.append(total / used_weight if used_weight else values[index])
    return smoothed


def estimate_linear_baseline(
    rt: Sequence[float],
    values: Sequence[float],
    baseline_window_min: float | None,
) -> list[float]:
    """Estimate a line between median intensities at both edges of a window."""

    if not values:
        return []
    if len(values) == 1 or rt[-1] == rt[0]:
        return [values[0] for _ in values]

    window = baseline_window_min or max((rt[-1] - rt[0]) * 0.1, 0.0)
    left_values = [value for time, value in zip(rt, values) if time <= rt[0] + window]
    right_values = [value for time, value in zip(rt, values) if time >= rt[-1] - window]
    minimum_edge_count = max(1, min(5, len(values) // 5))
    if len(left_values) < minimum_edge_count:
        left_values = list(values[:minimum_edge_count])
    if len(right_values) < minimum_edge_count:
        right_values = list(values[-minimum_edge_count:])

    left = median(left_values)
    right = median(right_values)
    span = rt[-1] - rt[0]
    return [left + ((time - rt[0]) / span) * (right - left) for time in rt]


def estimate_noise(
    corrected: Sequence[float],
    baseline_window_min: float | None,
    rt: Sequence[float],
) -> float:
    if len(corrected) < 2:
        return 0.0
    window = baseline_window_min or max((rt[-1] - rt[0]) * 0.1, 0.0)
    edge_values = [
        value
        for time, value in zip(rt, corrected)
        if time <= rt[0] + window or time >= rt[-1] - window
    ]
    if len(edge_values) < 2:
        edge_count = max(1, min(5, len(corrected) // 5))
        edge_values = list(corrected[:edge_count]) + list(corrected[-edge_count:])
    average = sum(edge_values) / len(edge_values)
    variance = sum((value - average) ** 2 for value in edge_values) / max(1, len(edge_values) - 1)
    return math.sqrt(variance)


def find_candidate_apices(
    corrected: Sequence[float],
    *,
    min_height: float,
    noise: float,
    min_separation_points: int,
) -> list[int]:
    threshold = max(min_height, noise * 3.0)
    if not corrected:
        return []

    candidates: list[int] = []
    for index in range(1, len(corrected) - 1):
        if corrected[index] < threshold:
            continue
        is_peak = corrected[index] >= corrected[index - 1] and corrected[index] >= corrected[index + 1]
        is_not_flat = corrected[index] > corrected[index - 1] or corrected[index] > corrected[index + 1]
        if is_peak and is_not_flat:
            candidates.append(index)

    if not candidates:
        max_index = max(range(len(corrected)), key=lambda idx: corrected[idx])
        if corrected[max_index] >= threshold:
            candidates = [max_index]

    separated: list[int] = []
    for index in sorted(candidates, key=lambda idx: corrected[idx], reverse=True):
        if all(abs(index - kept) >= max(1, min_separation_points) for kept in separated):
            separated.append(index)
    return sorted(separated)


def classify_peak(
    *,
    entry: PeakGuideEntry,
    rt: Sequence[float],
    corrected: Sequence[float],
    candidates: Sequence[int],
    noise: float,
) -> CategorySet:
    if not corrected or not candidates:
        return CategorySet(peak_shape="Noisy", baseline="Noisy", qc_action="Reject")

    main_index = max(candidates, key=lambda idx: corrected[idx])
    height = corrected[main_index]
    noise_percent = (noise / height * 100.0) if height > 0 else 100.0
    baseline_limit = entry.noise_percentage if entry.noise_percentage is not None else 50.0
    baseline = "Noisy" if noise_percent > baseline_limit else "Stable"
    interference = "Co-eluting" if len(candidates) > 1 else "None"

    comparable_secondary = [
        idx for idx in candidates if idx != main_index and corrected[idx] >= height * 0.25
    ]
    if comparable_secondary:
        peak_shape = "Split" if len(comparable_secondary) > 1 else "Shoulder"
    else:
        peak_shape = classify_shape_by_half_width(corrected, main_index)

    retention_shift = "None"
    if entry.expected_rt_min is not None:
        half_window = (entry.rt_half_window_sec or 30.0) / 60.0
        shift = rt[main_index] - entry.expected_rt_min
        if abs(shift) > half_window * 0.5:
            retention_shift = "Late" if shift > 0 else "Early"

    qc_action = "Accept" if baseline != "Noisy" or entry.after.qc_action.casefold() == "accept" else "Review"
    return CategorySet(
        peak_shape=peak_shape,
        baseline=baseline,
        interference=interference,
        retention_shift=retention_shift,
        qc_action=qc_action,
    )


def classify_shape_by_half_width(corrected: Sequence[float], apex_index: int) -> str:
    apex = corrected[apex_index]
    if apex <= 0:
        return "Noisy"
    half_height = apex * 0.5
    left = apex_index
    while left > 0 and corrected[left] > half_height:
        left -= 1
    right = apex_index
    while right < len(corrected) - 1 and corrected[right] > half_height:
        right += 1

    left_width = max(1, apex_index - left)
    right_width = max(1, right - apex_index)
    ratio = right_width / left_width
    if ratio >= 1.4:
        return "Tailing"
    if ratio <= 1 / 1.4:
        return "Fronting"
    return "Clean"


def select_apex_index(
    entry: PeakGuideEntry,
    rt: Sequence[float],
    candidates: Sequence[int],
) -> int:
    if not candidates:
        raise ValueError("Cannot select an apex without candidates")

    preference = entry.target_peak_preference
    if preference == "left":
        return min(candidates, key=lambda idx: rt[idx])
    if preference == "right":
        return max(candidates, key=lambda idx: rt[idx])
    if entry.expected_rt_min is None:
        return candidates[len(candidates) // 2]
    return min(candidates, key=lambda idx: abs(rt[idx] - entry.expected_rt_min))


def find_integration_bounds(
    *,
    entry: PeakGuideEntry,
    corrected: Sequence[float],
    apex_index: int,
    candidates: Sequence[int],
    noise: float,
) -> tuple[int, int]:
    height = corrected[apex_index]
    fraction = boundary_height_fraction(entry)
    threshold = max(noise * 2.0, height * fraction)

    left = apex_index
    while left > 0 and corrected[left] > threshold:
        left -= 1
    right = apex_index
    while right < len(corrected) - 1 and corrected[right] > threshold:
        right += 1

    previous_candidates = [idx for idx in candidates if idx < apex_index]
    next_candidates = [idx for idx in candidates if idx > apex_index]
    if previous_candidates:
        previous = max(previous_candidates)
        if previous >= left:
            left = min(range(previous, apex_index + 1), key=lambda idx: corrected[idx])
    if next_candidates:
        following = min(next_candidates)
        if following <= right:
            right = min(range(apex_index, following + 1), key=lambda idx: corrected[idx])

    min_width = entry.min_peak_width_points or 3
    while right - left + 1 < min_width and (left > 0 or right < len(corrected) - 1):
        if left > 0:
            left -= 1
        if right < len(corrected) - 1 and right - left + 1 < min_width:
            right += 1
    return left, right


def boundary_height_fraction(entry: PeakGuideEntry) -> float:
    text = f"{entry.integration_notes} {entry.before.peak_shape} {entry.after.peak_shape}".casefold()
    if "tighten" in text or "exclude tail" in text or "exclude tails" in text:
        return 0.03
    if "thin peak" in text:
        return 0.02
    if "broad peak" in text:
        return 0.01
    return 0.015


def trapezoid_area(rt: Sequence[float], values: Sequence[float]) -> float:
    if len(rt) < 2:
        return 0.0
    return sum(
        (rt[index + 1] - rt[index]) * (values[index] + values[index + 1]) / 2.0
        for index in range(len(rt) - 1)
    )


def compare_to_manual(
    results: Iterable[IntegrationResult],
    manual_areas: dict[tuple[str, str], ManualArea],
) -> list[IntegrationResult]:
    compared: list[IntegrationResult] = []
    for result in results:
        key = (result.sample_id, normalize_compound_name(result.compound))
        manual = manual_areas.get(key)
        if manual is not None:
            result.manual_area = manual.area
            if result.area is not None:
                result.area_error = result.area - manual.area
                result.relative_area_error = (
                    result.area_error / manual.area if manual.area != 0 else None
                )
        compared.append(result)
    return compared


def load_unintegrated_samples_csv(path: str | Path) -> dict[tuple[str, str], list[SamplePoint]]:
    """Load unintegrated sample points from CSV.

    Required logical columns are sample id, compound, retention time, and
    intensity.  Common aliases are accepted to make exported instrument data
    easier to use.
    """

    samples: dict[tuple[str, str], list[SamplePoint]] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Sample CSV has no header: {path}")
        fields = {field.casefold().strip(): field for field in reader.fieldnames}
        sample_col = _resolve_column(fields, "sample_id", "sample", "sample_name", "sample name", "file")
        compound_col = _resolve_column(
            fields,
            "compound",
            "current ms compounds",
            "analyte",
            "metabolite",
        )
        rt_col = _resolve_column(
            fields,
            "retention_time",
            "retention time",
            "rt",
            "rt_min",
            "time",
            "time_min",
        )
        intensity_col = _resolve_column(fields, "intensity", "abundance", "signal", "height")

        for line_number, row in enumerate(reader, start=2):
            sample_id = (row.get(sample_col) or "").strip()
            compound = (row.get(compound_col) or "").strip()
            if not sample_id or not compound:
                raise ValueError(f"Missing sample id or compound on line {line_number} of {path}")
            try:
                point = SamplePoint(
                    retention_time_min=float((row.get(rt_col) or "").strip()),
                    intensity=float((row.get(intensity_col) or "").strip()),
                )
            except ValueError as exc:
                raise ValueError(f"Invalid RT or intensity on line {line_number} of {path}") from exc
            samples.setdefault((sample_id, compound), []).append(point)
    return samples


def load_manual_areas_csv(path: str | Path) -> dict[tuple[str, str], ManualArea]:
    manual: dict[tuple[str, str], ManualArea] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Manual CSV has no header: {path}")
        fields = {field.casefold().strip(): field for field in reader.fieldnames}
        sample_col = _resolve_column(fields, "sample_id", "sample", "sample_name", "sample name", "file")
        compound_col = _resolve_column(fields, "compound", "current ms compounds", "analyte", "metabolite")
        area_col = _resolve_column(fields, "manual_area", "area", "integrated_area")
        start_col = _optional_column(fields, "start_rt_min", "start_rt", "manual_start_rt")
        end_col = _optional_column(fields, "end_rt_min", "end_rt", "manual_end_rt")

        for line_number, row in enumerate(reader, start=2):
            sample_id = (row.get(sample_col) or "").strip()
            compound = (row.get(compound_col) or "").strip()
            try:
                area = float((row.get(area_col) or "").strip())
                start_rt = _optional_row_float(row, start_col)
                end_rt = _optional_row_float(row, end_col)
            except ValueError as exc:
                raise ValueError(f"Invalid manual area on line {line_number} of {path}") from exc
            entry = ManualArea(sample_id, compound, area, start_rt, end_rt)
            manual[(sample_id, normalize_compound_name(compound))] = entry
    return manual


def write_results_csv(results: Iterable[IntegrationResult], path: str | Path) -> None:
    rows = [result.to_row() for result in results]
    fieldnames = [
        "sample_id",
        "compound",
        "integrated",
        "action",
        "observed_peak_shape",
        "observed_baseline",
        "observed_interference",
        "observed_retention_shift",
        "observed_qc_action",
        "guide_before",
        "guide_after",
        "start_rt_min",
        "apex_rt_min",
        "end_rt_min",
        "area",
        "raw_area",
        "peak_height",
        "manual_area",
        "area_error",
        "relative_area_error",
        "algorithm",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _resolve_column(fields: dict[str, str], *aliases: str) -> str:
    column = _optional_column(fields, *aliases)
    if column is None:
        raise ValueError(f"Missing required column. Expected one of: {', '.join(aliases)}")
    return column


def _optional_column(fields: dict[str, str], *aliases: str) -> str | None:
    for alias in aliases:
        field = fields.get(alias.casefold().strip())
        if field is not None:
            return field
    return None


def _optional_row_float(row: dict[str, str], column: str | None) -> float | None:
    if column is None:
        return None
    text = (row.get(column) or "").strip()
    if not text:
        return None
    return float(text)
