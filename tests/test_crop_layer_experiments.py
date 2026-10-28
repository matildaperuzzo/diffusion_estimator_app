"""Check the requested crop/layer matrix and report formatting."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from run_crop_layer_experiments import (CROPS, LAYER_SETS, collect_results,
                                        format_table, refine_from_sea, select_nested_baselines)


class CropLayerExperimentTests(unittest.TestCase):
    @patch("run_crop_layer_experiments.run_crop_experiments")
    def test_collects_all_crop_layer_results_in_order(self, runner):
        def fake_run(crop, layer_sets, method, options):
            self.assertEqual(method, "fast_marching")
            self.assertTrue(options["apply_w"])
            self.assertEqual(options["num_points"], 3)
            self.assertEqual(options["theta_range"].shape, (2, len(layer_sets[0]) + 1))
            return [
                {"layers": list(layers), "fit_result": SimpleNamespace(
                    x=np.arange(len(layers) + 1, dtype=float), fun=float(len(layers) + 1))}
                for layers in layer_sets
            ]

        runner.side_effect = fake_run
        rows = collect_results(CROPS, "fast_marching", {"apply_w": True})

        self.assertEqual(len(rows), 18)
        self.assertEqual([crop for crop, _, _, _ in rows[::6]], list(CROPS))
        self.assertEqual([layers for _, layers, _, _ in rows[:6]], list(LAYER_SETS))
        self.assertEqual(runner.call_count, 9)
        table = format_table(rows, "fast_marching", 40, 0.5, True, 100, 12, 5, 3)
        self.assertIn("| wheat | average only | 0 | 1.000 |", table)
        self.assertIn("| maize | hydro + sea | 0, 1, 2 | 3.000 |", table)
        self.assertEqual(sum(line.startswith("| ") for line in table.splitlines()), 20)

    def test_nested_model_is_never_worse_than_sea(self):
        rows = [
            ("wheat", (), np.array([-0.5]), 10.0),
            ("wheat", ("sea",), np.array([-1.0, 2.0]), 8.0),
            ("wheat", ("prec", "sea"), np.array([0.0, 1.0, 1.0]), 9.0),
        ]
        selected = select_nested_baselines(rows)
        np.testing.assert_array_equal(selected[2][2], [-1.0, 0.0, 2.0])
        self.assertEqual(selected[2][3], 8.0)

    @patch("run_crop_layer_experiments.run_crop_experiments")
    def test_refines_only_a_combined_model_worse_than_sea(self, runner):
        runner.return_value = [{"fit_result": SimpleNamespace(
            x=np.array([-1.0, 0.4, 2.0]), fun=7.0)}]
        rows = [
            ("wheat", (), np.array([-0.5]), 10.0),
            ("wheat", ("sea",), np.array([-1.0, 2.0]), 8.0),
            ("wheat", ("prec", "sea"), np.array([0.0, 1.0, 1.0]), 9.0),
            ("wheat", ("tmean", "sea"), np.array([0.0, 1.0, 1.0]), 6.0),
        ]
        refined = refine_from_sea(rows, "fast_marching", {"theta_bounds": (-5, 5)})
        self.assertEqual(refined[2][3], 7.0)
        self.assertEqual(refined[3][3], 6.0)
        self.assertEqual(runner.call_count, 1)
        np.testing.assert_array_equal(runner.call_args.args[3]["theta_start"], [-1.0, 0.0, 2.0])


if __name__ == "__main__":
    unittest.main()
