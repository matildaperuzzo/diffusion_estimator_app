# Diffusion Estimator App

`diffusion_estimator.py` estimates when a crop reaches locations in a geographic grid and compares those arrival times with observed crop dates. It loads processed HDF5 observations and environmental layers from `data/processed/`.

## Estimator

`DiffusionEstimator(crop, layers, delta=0.5, dt=40)` supports `wheat`, `rice`, and `maize`. Common model layers are `sea`, `prec`, `tmean`, `csi`, and `hydro`; use `[]` for an intercept-only model. Theta has one intercept followed by one coefficient per layer, in the listed order.

- `build_speed(theta)` applies a sigmoid to the weighted layer sum, producing a speed map.
- `get_arrival_times(speed, method=...)` propagates from the earliest crop observation using `fast_marching` or `monte_carlo`. Both apply the cosine-latitude weight by default (`apply_w=True`).
- `calculate_error(arrival_times)` returns mean squared arrival-time error in years squared.
- `sweep_theta(...)` searches a parameter grid; `fit_theta(...)` refines a starting theta with projected gradient descent. Fitted values are local results, not guaranteed global minima.

The climate layers are averaged over the crop's observed-year window when loaded. See [data processing](processing/DATA_PROCESSING.md) for layer sources and normalization details.

## Run experiments

From the repository root, run the prepared experiment script with the project's Python environment:

```powershell
.\.venv\Scripts\python.exe run_crop_layer_experiments.py
```

It fits 18 models: average-only, sea, and sea with each of precipitation, temperature, CSI, and hydro for all three crops. It writes [the theta and squared-error table](results/crop_layer_experiments.md). Monte Carlo, `delta=0.5`, `dt=40`, latitude weighting, theta bounds of `[-5, 5]`, and a three-point starting sweep are the defaults. Use `--method fast_marching` for fast marching fits, or `--help` for all options.

For a custom model, call the runners directly:

```python
from diffusion_estimator import run_experiment, run_crop_experiments

options = {
    "theta_range": [[-2, -5, -5], [2, 5, 5]],  # intercept, layer, sea
    "num_points": 3,
    "theta_bounds": (-5, 5),
}
one = run_experiment("wheat", ["prec", "sea"], "fast_marching", options)
print(one["fit_result"].x, one["fit_result"].fun)
print(one["result_path"])

many = run_crop_experiments(
    "wheat", [["prec", "sea"], ["tmean", "sea"]], "fast_marching", options
)
```

`run_experiment` returns the estimator, fit result, optional sweep result, and `result_path` in a dictionary. It automatically writes one JSON result per optimizer call to `generated_data/`. The result records effective inputs, theta, squared error, termination status, history, and data/code provenance; `OptimizationResult.from_json(path)` reads it back. `run_crop_experiments` returns one such dictionary per layer list. Shared sweep bounds must match the parameter count of every layer list. In `method_options`, use either `theta_start` or `theta_range` with `num_points`; `delta`, `dt`, `n_reps`, `random_state`, `apply_w`, and `result_directory` are also supported.

For Monte Carlo runs, the estimator calculates MATLAB's frame count automatically: `T = round((ceil(max(years)/dt)*dt + 1000 - floor(min(years)/dt)*dt)/dt + 1)`. An explicit `time_horizon` (or CLI `--time-horizon`) overrides it. Python stores zero-based arrival times, so a cell unreached by MATLAB frame T is assigned T−1. The default seed is 12, but NumPy's random stream is not MATLAB Threefry, so equal seeds do not reproduce MATLAB's draws.
