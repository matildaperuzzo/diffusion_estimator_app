"""Check the optional latitude weight in both diffusion solvers and their estimator API."""

# Keep solver checks independent of processed layer files and crop observations.
import unittest

import numpy as np

from diffusion_estimator import DiffusionEstimator
from fast_marching import fast_marching
from monte_carlo import calculate_simulation_times_and_error, simulate_arrival_times


class SpatialWeightTests(unittest.TestCase):
    """Exercise the cosine weight with small grids whose outcomes are explicit."""

    def test_monte_carlo_weight_changes_fixed_random_draw(self) -> None:
        """Apply MATLAB's W to a random draw at 60 degrees by default."""
        # With seed 42, the first frontier draw is about 0.439: 0.5 * draw
        # clears probability 0.3, while the unweighted draw does not.
        speed = np.full((1, 2), 0.3)
        starts = [(0, 0, 0)]
        weighted = simulate_arrival_times(speed, starts, 1, random_state=42, latitudes=[60.0])
        unweighted = simulate_arrival_times(
            speed, starts, 1, random_state=42, latitudes=[60.0], apply_w=False
        )

        # The second unweighted draw also fails before the two-step horizon ends.
        np.testing.assert_array_equal(weighted, [[0.0, 1.0]])
        self.assertEqual(unweighted[0, 0], 0.0)
        self.assertTrue(np.isinf(unweighted[0, 1]))

    def test_fast_marching_uses_weight_once_in_both_directions(self) -> None:
        """Scale north-south and east-west arrival times equally by W."""
        # Constant 60-degree latitude gives W=0.5 on every row; the direct
        # neighbour time is W/speed = 1 with weighting and 1/speed = 2 without.
        speed = np.full((3, 3), 0.5)
        starts = [(1, 1, 0)]
        neighbours = ((0, 1), (2, 1), (1, 0), (1, 2))
        weighted = fast_marching(speed, starts, latitudes=[60.0] * 3)
        unweighted = fast_marching(speed, starts, latitudes=[60.0] * 3, apply_w=False)

        # Comparing both axes catches a second cosine factor on longitude steps.
        for row, column in neighbours:
            self.assertAlmostEqual(weighted[row, column], 1.0)
            self.assertAlmostEqual(unweighted[row, column], 2.0)

    def test_estimator_forwards_weight_at_nondefault_delta(self) -> None:
        """Pass the loaded latitude and apply_w choice through both estimator paths."""
        # Build a minimal estimator with a quarter-degree grid setting, so the
        # forwarding check needs no real HDF5 layers or observation files.
        estimator = object.__new__(DiffusionEstimator)
        estimator.delta = 0.25
        estimator.dt = 40.0
        estimator.latitude = np.array([60.0, 59.75, 59.5])
        estimator.start_points = np.array([[1, 1, 0]])
        estimator.dataset = np.array([[0, 1, 1]])
        speed = np.full((3, 3), 0.3)

        # Verify that the same choice reaches each solver through get_arrival_times.
        weighted_mc = estimator.get_arrival_times(
            speed, method="monte_carlo", n_reps=1, random_state=42
        )
        unweighted_mc = estimator.get_arrival_times(
            speed, method="monte_carlo", n_reps=1, random_state=42, apply_w=False
        )
        weighted_fm = estimator.get_arrival_times(speed, method="fast_marching")
        unweighted_fm = estimator.get_arrival_times(
            speed, method="fast_marching", apply_w=False
        )
        self.assertEqual(weighted_mc[0, 1], 1.0)
        self.assertEqual(unweighted_mc[0, 1], 4.0)
        self.assertAlmostEqual(weighted_fm[0, 1], 0.5 / 0.3)
        self.assertAlmostEqual(unweighted_fm[0, 1], 1.0 / 0.3)

        # The estimator's direct Monte Carlo error method must forward W too.
        weighted_times, weighted_error = estimator.calculate_simulation_times_and_error(
            speed, n_reps=1, random_state=42
        )
        unweighted_times, unweighted_error = estimator.calculate_simulation_times_and_error(
            speed, n_reps=1, random_state=42, apply_w=False
        )
        np.testing.assert_array_equal(weighted_times, weighted_mc)
        np.testing.assert_array_equal(unweighted_times, unweighted_mc)
        self.assertEqual(weighted_error, 0.0)
        self.assertEqual(unweighted_error, (3.0 * estimator.dt) ** 2)

    def test_monte_carlo_error_function_forwards_explicit_weight(self) -> None:
        """Use an explicit W grid in the low-level error calculation."""
        # An explicit W must have the same effect as the equivalent latitude.
        speed = np.full((1, 2), 0.3)
        dataset = np.array([[0, 1, 1]])
        times, error = calculate_simulation_times_and_error(
            speed, dataset, [(0, 0, 0)], 1, dt=40.0, random_state=42, W=np.full((1, 2), 0.5)
        )
        np.testing.assert_array_equal(times, [[0.0, 1.0]])
        self.assertEqual(error, 0.0)


if __name__ == "__main__":
    # Allow the focused checks to run directly as well as under discovery.
    unittest.main()
