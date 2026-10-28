"""Check that experiment runners wire model setup and fitting correctly."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

import diffusion_estimator as estimator_module
from diffusion_estimator import DiffusionEstimator, run_crop_experiments, run_experiment


class ExperimentRunnerTests(unittest.TestCase):
    @patch("diffusion_estimator.DiffusionEstimator")
    def test_single_experiment_forwards_solver_and_options(self, estimator_class):
        estimator = estimator_class.return_value
        estimator.crop = "wheat"
        fit = SimpleNamespace(x=np.array([1.0, 2.0]), fun=3.0)
        estimator.fit_theta.return_value = fit
        options = {"theta_start": [0.5, -0.5], "dt": 20, "n_reps": 8,
                   "random_state": 12, "apply_w": False}

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

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_optional_sweep_supplies_fit_start(self, estimator_class):
        estimator = estimator_class.return_value
        estimator.crop = "wheat"
        estimator.sweep_theta.return_value = (np.array([0.3, -0.4]), 42.0)
        bounds = np.array([[-1.0, -2.0], [1.0, 2.0]])

        result = run_experiment(
            "wheat", ["sea"], "fast_marching",
            {"theta_range": bounds, "num_points": 3, "apply_w": False},
        )

        np.testing.assert_array_equal(estimator.sweep_theta.call_args.args[0], bounds)
        self.assertEqual(estimator.sweep_theta.call_args.kwargs["method"], "fast_marching")
        self.assertFalse(estimator.sweep_theta.call_args.kwargs["apply_w"])
        np.testing.assert_array_equal(estimator.fit_theta.call_args.args[0], [0.3, -0.4])
        self.assertEqual(result["sweep_result"]["error"], 42.0)

    @patch("diffusion_estimator.DiffusionEstimator")
    def test_batch_uses_independent_layer_lists(self, estimator_class):
        first = SimpleNamespace(crop="wheat", fit_theta=Mock(return_value="one"))
        second = SimpleNamespace(crop="wheat", fit_theta=Mock(return_value="two"))
        estimator_class.side_effect = [first, second]

        results = run_crop_experiments("wheat", [[], ["prec", "sea"]], "fast_marching")

        self.assertEqual([result["fit_result"] for result in results], ["one", "two"])
        self.assertEqual([result["layers"] for result in results], [[], ["prec", "sea"]])
        np.testing.assert_array_equal(first.fit_theta.call_args.args[0], [0.0])
        np.testing.assert_array_equal(second.fit_theta.call_args.args[0], [0.0, 0.0, 0.0])
        self.assertEqual(estimator_class.call_count, 2)

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
