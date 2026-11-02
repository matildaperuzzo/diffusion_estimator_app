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

It fits 18 models: average-only, sea, and sea with each of precipitation, temperature, CSI, and hydro for all three crops. It writes [the theta and squared-error table](results/crop_layer_experiments.md). Fast marching, `delta=0.5`, `dt=40`, latitude weighting, theta bounds of `[-5, 5]`, and a three-point starting sweep are the defaults. Use `--method monte_carlo --n-reps 100 --seed 12` for Monte Carlo fits, or `--help` for all options.

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

many = run_crop_experiments(
    "wheat", [["prec", "sea"], ["tmean", "sea"]], "fast_marching", options
)
```

`run_experiment` returns the estimator, fit result, and optional sweep result in a dictionary; `run_crop_experiments` returns one such dictionary per layer list. Shared sweep bounds must match the parameter count of every layer list. In `method_options`, use either `theta_start` or `theta_range` with `num_points`; `delta`, `dt`, `n_reps`, `random_state`, and `apply_w` are also supported.
