import csv
import math
import tempfile
import unittest
from pathlib import Path

from peak_processing.cli import main as cli_main
from peak_processing.guide import load_peak_processing_guide, normalize_compound_name
from peak_processing.integration import (
    ManualArea,
    PeakIntegrator,
    SamplePoint,
    compare_to_manual,
    load_unintegrated_samples_csv,
)


ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = ROOT / "data" / "peak_processing_guide.csv"


def gaussian_points(
    *,
    center: float,
    amplitude: float,
    sigma: float,
    start: float,
    end: float,
    step: float = 0.01,
    baseline: float = 1000.0,
) -> list[SamplePoint]:
    points = []
    count = int(round((end - start) / step)) + 1
    for idx in range(count):
        rt = start + idx * step
        signal = baseline + amplitude * math.exp(-0.5 * ((rt - center) / sigma) ** 2)
        points.append(SamplePoint(rt, signal))
    return points


class PeakProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.guide = load_peak_processing_guide(GUIDE_PATH)

    def test_loads_guide_categories_and_settings(self) -> None:
        glycine = self.guide[normalize_compound_name("Glycine")]

        self.assertEqual(glycine.compound, "Glycine")
        self.assertEqual(glycine.before.peak_shape, "Tailing")
        self.assertEqual(glycine.after.peak_shape, "Clean")
        self.assertEqual(glycine.expected_rt_min, 8.38)
        self.assertEqual(glycine.min_peak_height, 5000.0)

    def test_integrates_clean_synthetic_peak_and_compares_manual_area(self) -> None:
        points = gaussian_points(
            center=8.38,
            amplitude=120000.0,
            sigma=0.035,
            start=7.8,
            end=8.9,
        )
        result = PeakIntegrator(self.guide).integrate("sample-1", "Glycine", points)

        self.assertTrue(result.integrated)
        self.assertAlmostEqual(result.apex_rt_min, 8.38, places=2)
        self.assertGreater(result.area or 0.0, 9000.0)
        self.assertLess(result.start_rt_min or 0.0, result.apex_rt_min or 0.0)
        self.assertGreater(result.end_rt_min or 0.0, result.apex_rt_min or 0.0)
        self.assertIn("trapezoidal", " ".join(result.algorithm_steps))

        compared = compare_to_manual(
            [result],
            {("sample-1", normalize_compound_name("Glycine")): ManualArea("sample-1", "Glycine", 10500.0)},
        )[0]
        self.assertIsNotNone(compared.area_error)
        self.assertIsNotNone(compared.relative_area_error)

    def test_guide_directs_left_peak_selection(self) -> None:
        points = []
        start = 4.7
        step = 0.01
        for idx in range(110):
            rt = start + idx * step
            left = 180000.0 * math.exp(-0.5 * ((rt - 5.18) / 0.025) ** 2)
            right = 160000.0 * math.exp(-0.5 * ((rt - 5.45) / 0.025) ** 2)
            points.append(SamplePoint(rt, 1000.0 + left + right))

        result = PeakIntegrator(self.guide).integrate("sample-1", "Trimethylamine (TMA)", points)

        self.assertTrue(result.integrated)
        self.assertAlmostEqual(result.apex_rt_min, 5.18, places=2)
        self.assertIn("Select left candidate", " ".join(result.algorithm_steps))

    def test_guide_can_request_no_integration(self) -> None:
        points = gaussian_points(
            center=4.5,
            amplitude=50000.0,
            sigma=0.04,
            start=4.0,
            end=5.0,
        )
        result = PeakIntegrator(self.guide).integrate("sample-1", "Aminoacetone", points)

        self.assertFalse(result.integrated)
        self.assertEqual(result.action, "Reject")
        self.assertIn("request no integration", " ".join(result.algorithm_steps))

    def test_loads_samples_and_cli_writes_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            samples_path = temp / "samples.csv"
            output_path = temp / "results.csv"
            points = gaussian_points(
                center=8.38,
                amplitude=100000.0,
                sigma=0.035,
                start=7.8,
                end=8.9,
                step=0.02,
            )
            with samples_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["sample_id", "compound", "rt", "intensity"])
                for point in points:
                    writer.writerow(
                        ["sample-1", "Glycine", point.retention_time_min, point.intensity]
                    )

            loaded = load_unintegrated_samples_csv(samples_path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(len(next(iter(loaded.values()))), len(points))

            exit_code = cli_main(
                [
                    "--guide",
                    str(GUIDE_PATH),
                    "--samples",
                    str(samples_path),
                    "--output",
                    str(output_path),
                ]
            )
            self.assertEqual(exit_code, 0)
            with output_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["compound"], "Glycine")
            self.assertEqual(rows[0]["integrated"], "yes")
            self.assertIn("algorithm", rows[0])


if __name__ == "__main__":
    unittest.main()
