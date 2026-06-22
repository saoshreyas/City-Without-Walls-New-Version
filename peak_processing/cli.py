"""Command-line interface for guide-driven peak integration."""

from __future__ import annotations

import argparse

from .guide import load_peak_processing_guide
from .integration import (
    PeakIntegrator,
    compare_to_manual,
    load_manual_areas_csv,
    load_unintegrated_samples_csv,
    write_results_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Integrate unprocessed chromatogram samples using a peak processing "
            "guide and output the selected integration algorithm for each peak."
        )
    )
    parser.add_argument(
        "--guide",
        required=True,
        help="Path to the peak processing guide CSV.",
    )
    parser.add_argument(
        "--samples",
        required=True,
        help=(
            "CSV of unintegrated points. Required columns: sample_id, compound, "
            "retention_time (or rt), intensity."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for the integration result CSV.",
    )
    parser.add_argument(
        "--manual",
        help=(
            "Optional CSV of manual/correct integrations. Required columns: "
            "sample_id, compound, manual_area (or area)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    guide = load_peak_processing_guide(args.guide)
    samples = load_unintegrated_samples_csv(args.samples)
    results = PeakIntegrator(guide).integrate_many(samples)
    if args.manual:
        results = compare_to_manual(results, load_manual_areas_csv(args.manual))
    write_results_csv(results, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
