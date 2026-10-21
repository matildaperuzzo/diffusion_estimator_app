"""Monte Carlo front-propagation solver for the diffusion estimator."""

# Import NumPy for array operations and reproducible random sampling.
import numpy as np


def _frontier(active: np.ndarray) -> np.ndarray:
    """Return cells adjacent to at least one active cell."""
    # Pad the active grid so edge cells can be shifted without wrapping around.
    padded = np.pad(active, 1, mode="constant", constant_values=False)
    north = padded[:-2, 1:-1]
    south = padded[2:, 1:-1]
    west = padded[1:-1, :-2]
    east = padded[1:-1, 2:]
    return (~active) & (north | south | west | east)


def simulate_arrival_times(
    speed: np.ndarray,
    start_points: list[tuple[float, float, float]],
    n_reps: int,
    random_state: int | np.random.Generator | None = None,
) -> np.ndarray:
    """Average first-adoption times over Monte Carlo front simulations.

    ``speed`` is interpreted as a cell-wise adoption probability, matching the
    sigmoid output of the estimator's speed builder. Unreached cells retain
    ``np.inf`` in each repetition and in the returned average.
    """
    # Validate the simulation count before allocating potentially large arrays.
    if n_reps <= 0:
        raise ValueError("n_reps must be a positive integer.")
    if int(n_reps) != n_reps:
        raise ValueError("n_reps must be an integer.")

    # Convert the speed field to floating point probabilities and validate it.
    probabilities = np.asarray(speed, dtype=float)
    if probabilities.ndim != 2:
        raise ValueError("speed must be a two-dimensional array.")
    if np.any((probabilities < 0.0) | (probabilities > 1.0)):
        raise ValueError("speed values must be between zero and one.")

    # Accept either a seed or an existing generator for reproducible runs.
    rng = random_state if isinstance(random_state, np.random.Generator) else np.random.default_rng(random_state)
    shape = probabilities.shape
    starts = [(int(point[0]), int(point[1])) for point in start_points]
    for row, column in starts:
        if not (0 <= row < shape[0] and 0 <= column < shape[1]):
            raise IndexError("A start point is outside the speed grid.")

    # Accumulate finite values and counts so unreached cells do not poison the mean.
    time_sum = np.zeros(shape, dtype=float)
    time_count = np.zeros(shape, dtype=np.int64)
    for _ in range(int(n_reps)):
        # Mark all supplied start points active at simulation time zero.
        active = np.zeros(shape, dtype=bool)
        arrival = np.full(shape, np.inf, dtype=float)
        for row, column in starts:
            active[row, column] = True
            arrival[row, column] = 0.0

        # Advance one discrete timestep until the frontier is exhausted.
        for timestep in range(1, shape[0] * shape[1] + 1):
            frontier = _frontier(active)
            if not np.any(frontier):
                break
            adopted = frontier & (rng.random(shape) <= probabilities)
            if not np.any(adopted):
                continue
            active[adopted] = True
            arrival[adopted] = timestep

        reached = np.isfinite(arrival)
        time_sum[reached] += arrival[reached]
        time_count[reached] += 1

    # Return the mean where at least one simulation reached a cell.
    average = np.full(shape, np.inf, dtype=float)
    reached = time_count > 0
    average[reached] = time_sum[reached] / time_count[reached]
    return average


def calculate_simulation_times_and_error(
    speed: np.ndarray,
    dataset: np.ndarray,
    start_points: list[tuple[float, float, float]],
    n_reps: int,
    dt: float = 1.0,
    random_state: int | np.random.Generator | None = None,
) -> tuple[np.ndarray, float]:
    """Calculate averaged simulation times and their mean squared error."""
    # Run the stochastic solver once, then compare only the observed data cells.
    simulation_times = simulate_arrival_times(speed, start_points, n_reps, random_state)
    observations = np.asarray(dataset)
    indices = observations[:, :2].astype(int)
    predicted = simulation_times[indices[:, 0], indices[:, 1]]
    errors = (observations[:, 2] - predicted) * dt
    return simulation_times, float(np.mean(errors**2))


if __name__ == "__main__":
    # Import plotting only for the interactive demonstration so the solver stays lightweight.
    import matplotlib.pyplot as plt

    # Import the estimator to load the processed crop and geography layers.
    from diffusion_estimator import DiffusionEstimator

    # Define a small, reproducible single-theta example for manual inspection.
    crop_name = "wheat"
    layer_names = ["prec", "sea"]
    theta = np.array([0.0, 1.0, 1.0], dtype=float)
    repetitions = 1
    estimator = DiffusionEstimator(crop_name, layer_names)
    speed = estimator.build_speed(theta)

    # Calculate the averaged Monte Carlo field and the observed-data error.
    arrival_times, mean_squared_error = estimator.calculate_simulation_times_and_error(
        speed,
        n_reps=repetitions,
        random_state=42,
    )
    print(f"Crop: {crop_name}")
    print(f"Layers: {', '.join(layer_names)}")
    print(f"Theta: {theta}")
    print(f"Monte Carlo repetitions: {repetitions}")
    print(f"Mean squared error: {mean_squared_error:.6f}")

    # Place the observed crop-point times onto the estimator grid for plotting.
    observed_data = np.full(speed.shape, np.nan, dtype=float)
    observed_indices = estimator.dataset[:, :2].astype(int)
    observed_data[observed_indices[:, 0], observed_indices[:, 1]] = estimator.dataset[:, 2]

    # Build one figure containing the crop footprint, true observations, input layers, and MC result.
    fields = [("True crop data", observed_data)]
    fields.extend((f"Layer: {name}", values) for name, values in estimator.layer_data.items())
    fields.append(("Mean arrival time", arrival_times))
    figure, axes = plt.subplots(1, len(fields), figsize=(5 * len(fields), 4), squeeze=False)
    for axis, (title, field) in zip(axes[0], fields):
        # Mask unreachable cells so their infinite arrival times do not distort the colour scale.
        display_field = np.ma.masked_invalid(np.where(np.isfinite(field), field, np.nan))
        image = axis.imshow(display_field, origin="upper", aspect="auto", cmap="viridis")
        axis.set_title(title)
        axis.set_xlabel("Longitude index")
        axis.set_ylabel("Latitude index")
        figure.colorbar(image, ax=axis, shrink=0.8)

    # Display the interactive plots after all fields have been prepared.
    figure.suptitle("Monte Carlo diffusion estimator test")
    figure.tight_layout()
    plt.show()

    print("Monte Carlo diffusion estimator test completed successfully.")
