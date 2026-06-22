"""Parsing for the peak processing guide CSV.

The uploaded guide uses two header rows.  Columns 20-24 describe the peak
state before integration and columns 26-30 describe the desired state after
integration.  The numerical integration settings live in columns 11-18.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _clean(value: object) -> str:
    return str(value or "").strip()


def _optional_float(value: object) -> float | None:
    text = _clean(value)
    if not text or text.upper() in {"N/A", "NA", "#VALUE!"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _optional_int(value: object) -> int | None:
    number = _optional_float(value)
    if number is None:
        return None
    return int(round(number))


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return _clean(row[index])


@dataclass(frozen=True)
class CategorySet:
    """Qualitative peak categories from the guide."""

    peak_shape: str = ""
    baseline: str = ""
    interference: str = ""
    retention_shift: str = ""
    qc_action: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "peak_shape": self.peak_shape,
            "baseline": self.baseline,
            "interference": self.interference,
            "retention_shift": self.retention_shift,
            "qc_action": self.qc_action,
        }

    def summary(self) -> str:
        parts = [
            self.peak_shape,
            self.baseline,
            self.interference,
            self.retention_shift,
            self.qc_action,
        ]
        return " | ".join(part for part in parts if part)


@dataclass(frozen=True)
class PeakGuideEntry:
    """One compound row from the peak processing guide."""

    compound: str
    esi_mode: str = ""
    molecular_formula: str = ""
    cas: str = ""
    pathways: str = ""
    original_expected_rt_min: float | None = None
    peak_rating: str = ""
    notes: str = ""
    integration_notes: str = ""
    gaussian_smooth_width_points: float | None = None
    expected_rt_min: float | None = None
    rt_half_window_sec: float | None = None
    min_peak_width_points: int | None = None
    min_peak_height: float | None = None
    noise_percentage: float | None = None
    baseline_sub_window_min: float | None = None
    peak_splitting_points: int | None = None
    before: CategorySet = CategorySet()
    after: CategorySet = CategorySet()

    @property
    def key(self) -> str:
        return normalize_compound_name(self.compound)

    @property
    def should_reject(self) -> bool:
        """Whether the guide explicitly calls for no integration."""

        action = self.after.qc_action.casefold()
        notes = self.integration_notes.casefold()
        reject_phrases = (
            "no peaks integrated",
            "no defined peak",
            "not integrated",
            "noisy, no",
        )
        return "reject" in action or any(phrase in notes for phrase in reject_phrases)

    @property
    def target_peak_preference(self) -> str:
        """Return left/right/closest based on guide action and notes."""

        text = f"{self.integration_notes} {self.before.qc_action} {self.after.qc_action}"
        text = text.casefold()
        if "choose left" in text or "left peak only" in text or "peak on the left" in text:
            return "left"
        if "choose right" in text or "right peak only" in text or "peak on the right" in text:
            return "right"
        return "closest"


def normalize_compound_name(name: str) -> str:
    """Normalize compound names for case-insensitive exact matching."""

    return " ".join(_clean(name).casefold().split())


def load_peak_processing_guide(path: str | Path) -> dict[str, PeakGuideEntry]:
    """Load guide entries keyed by normalized compound name.

    Blank compound rows are skipped.  If the sheet contains duplicate compound
    names, the last nonblank row wins, matching typical spreadsheet update
    behavior.
    """

    entries: dict[str, PeakGuideEntry] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        rows = list(reader)

    if len(rows) < 3:
        raise ValueError(f"Guide CSV must contain at least two header rows: {path}")

    for row in rows[2:]:
        compound = _cell(row, 0)
        if not compound:
            continue

        entry = PeakGuideEntry(
            compound=compound,
            esi_mode=_cell(row, 1),
            molecular_formula=_cell(row, 2),
            cas=_cell(row, 3),
            pathways=_cell(row, 4),
            original_expected_rt_min=_optional_float(_cell(row, 5)),
            peak_rating=_cell(row, 6),
            notes=_cell(row, 7),
            integration_notes=_cell(row, 10),
            gaussian_smooth_width_points=_optional_float(_cell(row, 11)),
            expected_rt_min=_optional_float(_cell(row, 12)),
            rt_half_window_sec=_optional_float(_cell(row, 13)),
            min_peak_width_points=_optional_int(_cell(row, 14)),
            min_peak_height=_optional_float(_cell(row, 15)),
            noise_percentage=_optional_float(_cell(row, 16)),
            baseline_sub_window_min=_optional_float(_cell(row, 17)),
            peak_splitting_points=_optional_int(_cell(row, 18)),
            before=CategorySet(
                peak_shape=_cell(row, 20),
                baseline=_cell(row, 21),
                interference=_cell(row, 22),
                retention_shift=_cell(row, 23),
                qc_action=_cell(row, 24),
            ),
            after=CategorySet(
                peak_shape=_cell(row, 26),
                baseline=_cell(row, 27),
                interference=_cell(row, 28),
                retention_shift=_cell(row, 29),
                qc_action=_cell(row, 30),
            ),
        )
        entries[entry.key] = entry

    return entries


def require_guide_entry(
    guide: dict[str, PeakGuideEntry],
    compound: str,
    *,
    known_names: Iterable[str] | None = None,
) -> PeakGuideEntry:
    """Find a compound in a loaded guide or raise a helpful error."""

    key = normalize_compound_name(compound)
    entry = guide.get(key)
    if entry is not None:
        return entry

    choices = sorted(known_names or (entry.compound for entry in guide.values()))
    preview = ", ".join(choices[:8])
    suffix = "..." if len(choices) > 8 else ""
    raise KeyError(f"Compound {compound!r} was not found in the guide. Known: {preview}{suffix}")
