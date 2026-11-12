"""Check that experiment runners wire model setup and fitting correctly."""

import unittest
import json
from pathlib import Path
import shutil
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy as np

import diffusion_estimator as estimator_module
from diffusion_estimator import DiffusionEstimator, run_crop_experiments, run_experiment
from optimization_result import OptimizationResult


def fake_fit(theta, error):
    return OptimizationResult(
        run_id="test" + str(len(theta)), started_at="2026-11-03T10:00:00+00:00",
        finished_at="2026-11-03T10:00:01+00:00", inputs={},
        outputs={"theta": theta, "squared_error_years2": error,
                 "iterations": 1, "objective_evaluations": 4,
                 "history": [], "success": True, "message": "test"},
        provenance={},
    )


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "generated_data"
        scratch.mkdir(exist_ok=True)
        self.output = scratch / f"test_{uuid4().hex}"
        self.output.mkdir()

        def cleanup():
            if self.output.resolve().parent != scratch.resolve():
                raise RuntimeError("Refusing to remove an unexpected test directory")
            shutil.rmtree(self.output)

        self.addCleanup(cleanup)

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_single_experiment_forwards_solver_and_options(self, estimator_class):
        estimator = estimator_class.return_value
        estimator.crop = "wheat"
        fit = fake_fit(np.array([1.0, 2.0]), 3.0)
        estimator.fit_theta.return_value = fit
        options = {"theta_start": [0.5, -0.5], "dt": 20, "n_reps": 8,
                   "random_state": 12, "apply_w": False,
                   "result_directory": self.output}

        result = run_experiment("wheat", ["sea"], "monte_carlo", options)

        estimator_class.assert_called_once_with("wheat", ["sea"], dt=20)
        args, kwargs = estimator.fit_theta.call_args
        np.testing.assert_array_equal(args[0], [0.5, -0.5])
        self.assertEqual(kwargs, {"method": "monte_carlo", "n_reps": 8,
                                  "random_state": 12, "apply_w": False})
        self.assertIs(result["fit_result"], fit)
        self.assertIs(result["estimator"], estimator)
        self.assertEqual(result["layers"], ["sea"])
        self.assertIsNone(result["sweep_result"])
        self.assertEqual(options["theta_start"], [0.5, -0.5])
        self.assertEqual(result["result_path"], fit.result_path)
        self.assertEqual(json.loads(fit.result_path.read_text())["inputs"]["initialization"]["source"], "provided")

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_optional_sweep_supplies_fit_start(self, estimator_class):
        estimator = estimator_class.return_value
        estimator.crop = "wheat"
        estimator.sweep_theta.return_value = (np.array([0.3, -0.4]), 42.0)
        estimator.objective_function = np.array([[0.3, -0.4, 42.0]])
        estimator.fit_theta.return_value = fake_fit(np.array([0.3, -0.4]), 42.0)
        bounds = np.array([[-1.0, -2.0], [1.0, 2.0]])

        result = run_experiment(
            "wheat", ["sea"], "fast_marching",
            {"theta_range": bounds, "num_points": 3, "apply_w": False,
             "result_directory": self.output},
        )

        np.testing.assert_array_equal(estimator.sweep_theta.call_args.args[0], bounds)
        self.assertEqual(estimator.sweep_theta.call_args.kwargs["method"], "fast_marching")
        self.assertFalse(estimator.sweep_theta.call_args.kwargs["apply_w"])
        np.testing.assert_array_equal(estimator.fit_theta.call_args.args[0], [0.3, -0.4])
        self.assertEqual(result["sweep_result"]["error"], 42.0)
        saved = json.loads(result["result_path"].read_text())
        self.assertEqual(saved["inputs"]["initialization"]["source"], "sweep")
        self.assertEqual(saved["inputs"]["initialization"]["sweep"]["evaluations"], [[0.3, -0.4, 42.0]])

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_batch_uses_independent_layer_lists(self, estimator_class):
        first_fit = fake_fit(np.array([0.0]), 1.0)
        second_fit = fake_fit(np.array([0.0, 0.0, 0.0]), 2.0)
        first = Mock(crop="wheat", fit_theta=Mock(return_value=first_fit))
        second = Mock(crop="wheat", fit_theta=Mock(return_value=second_fit))
        estimator_class.side_effect = [first, second]

        results = run_crop_experiments("wheat", [[], ["prec", "sea"]], "fast_marching",
                                       {"result_directory": self.output})

        self.assertEqual([result["fit_result"] for result in results], [first_fit, second_fit])
        self.assertEqual([result["layers"] for result in results], [[], ["prec", "sea"]])
        np.testing.assert_array_equal(first.fit_theta.call_args.args[0], [0.0])
        np.testing.assert_array_equal(second.fit_theta.call_args.args[0], [0.0, 0.0, 0.0])
        self.assertEqual(estimator_class.call_count, 2)

    def test_fit_record_contains_effective_inputs_and_round_trips(self):
        root = self.output
        (root / "crop").mkdir()
        (root / "layers").mkdir()
        (root / "crop" / "wheat.h5").write_bytes(b"crop")
        (root / "layers" / "sea.h5").write_bytes(b"sea")
        estimator = DiffusionEstimator.__new__(DiffusionEstimator)
        estimator.crop, estimator.layers = "wheat", []
        estimator.dt, estimator.delta, estimator.buffer_size_rad = 40, 0.5, 0.0
        estimator.data_directory, estimator.dataset_is_override = root, False
        estimator.dataset = np.array([[0.0, 0.0, 0.0]])
        estimator.layer_data = {}
        estimator.start_points = np.array([[0.0, 0.0, 0.0]])
        estimator.grid_shape = (1, 1)
        estimator.latitude_extent = estimator.longitude_extent = (0.0, 1.0)
        estimator.year_extent = (-100.0, 0.0)
        estimator.build_speed = lambda theta: np.array([[theta[0]]])
        estimator.get_arrival_times = lambda speed, **kwargs: speed
        estimator.calculate_error = lambda times: float((times[0, 0] - 1.0) ** 2)

        result = estimator.fit_theta([0.0], theta_bounds=(-2, 2))
        saved_path = result.save_json(root / "run.json")
        loaded = OptimizationResult.from_json(saved_path)
        self.assertTrue(loaded.success)
        self.assertEqual(loaded.outputs["status"], "gradient_tolerance")
        self.assertEqual(loaded.nfev, 4)
        self.assertEqual(loaded.inputs["optimizer"]["theta_bounds"], [[-2.0, 2.0]])
        self.assertEqual(loaded.inputs["data"]["dataset"]["shape"], [1, 3])
        np.testing.assert_array_equal(loaded.x, [0.0])

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_invalid_options_fail_before_loading_data(self, estimator_class):
        with self.assertRaisesRegex(TypeError, "Unknown method_options"):
            run_experiment("wheat", ["sea"], "fast_marching", {"unknown": 1})
        with self.assertRaisesRegex(ValueError, "theta_start"):
            run_experiment("wheat", ["sea"], "fast_marching", {"theta_start": [0.0]})
        with self.assertRaisesRegex(ValueError, "theta_range and num_points"):
            run_experiment("wheat", ["sea"], "fast_marching", {"num_points": 3})
        with self.assertRaisesRegex(ValueError, "method"):
            run_experiment("wheat", ["sea"], "unknown")
        estimator_class.assert_not_called()

    def test_sweep_runs_without_optional_tqdm(self):
        estimator = DiffusionEstimator.__new__(DiffusionEstimator)
        estimator.objective_function = np.array([])
        estimator.build_speed = Mock(return_value=np.ones((1, 1)))
        estimator.get_arrival_times = Mock(return_value=np.ones((1, 1)))
        estimator.calculate_error = Mock(side_effect=[2.0, 1.0])

        with patch.object(estimator_module, "tqdm", None):
            theta, error = estimator.sweep_theta(np.array([[-1.0], [1.0]]), 2)

        np.testing.assert_array_equal(theta, [1.0])
        self.assertEqual(error, 1.0)


if __name__ == "__main__":
    unittest.main()
