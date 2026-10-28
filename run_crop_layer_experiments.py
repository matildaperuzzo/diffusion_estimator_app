"""Fit the requested crop/layer models and write a Markdown results table.

Example: python run_crop_layer_experiments.py --output results/crop_layer_experiments.md
"""

import argparse
from pathlib import Path

import numpy as np

from diffusion_estimator import run_crop_experiments


CROPS = ("wheat", "rice", "maize")
# Keep the environmental coefficient before sea, as in the MATLAB fits.
LAYER_SETS = (
    (),
    ("sea",),
    ("prec", "sea"),
    ("tmean", "sea"),
    ("csi", "sea"),
    ("hydro", "sea"),
)


def collect_results(crops, method, method_options, sweep_points=3, theta_limit=5.0):
    """Sweep and fit every layer set for each crop; preserve the requested order."""
    rows = []
    for crop in crops:
        print(f"Fitting {crop}: {len(LAYER_SETS)} layer sets", flush=True)
        # A shared theta_range must have the same dimension for every batch member.
        for layer_group in (LAYER_SETS[:1], LAYER_SETS[1:2], LAYER_SETS[2:]):
            coefficient_count = len(layer_group[0]) + 1
            limits = np.full(coefficient_count, theta_limit, dtype=float)
            limits[0] = min(theta_limit, 2.0)
            options = dict(method_options)
            options.update({"theta_range": np.stack((-limits, limits)),
                            "num_points": sweep_points})
            experiments = run_crop_experiments(crop, layer_group, method, options)
            if len(experiments) != len(layer_group):
                raise RuntimeError(f"Expected {len(layer_group)} results for {crop}; got {len(experiments)}.")
            for expected_layers, experiment in zip(layer_group, experiments):
                layers = tuple(experiment["layers"])
                if layers != expected_layers:
                    raise RuntimeError(f"Unexpected layer order for {crop}: {layers}.")
                fit = experiment["fit_result"]
                theta = np.asarray(fit.x, dtype=float)
                squared_error = float(fit.fun)
                if theta.shape != (len(layers) + 1,) or not np.all(np.isfinite(theta)):
                    raise ValueError(f"Invalid fitted theta for {crop}, {layers}.")
                if not np.isfinite(squared_error):
                    raise ValueError(f"Invalid squared error for {crop}, {layers}.")
                rows.append((crop, layers, theta, squared_error))
                print(f"  {', '.join(layers) or 'average'}: {squared_error:,.3f} years^2", flush=True)
    return rows


def refine_from_sea(rows, method, method_options):
    """Try the fitted sea model as another start for weaker combined fits."""
    refined = []
    sea_by_crop = {}
    for crop, layers, theta, squared_error in rows:
        if layers == ("sea",):
            sea_by_crop[crop] = (theta, squared_error)
        elif len(layers) == 2:
            sea_theta, sea_error = sea_by_crop[crop]
            if squared_error > sea_error:
                start = np.array([sea_theta[0], 0.0, sea_theta[1]])
                options = dict(method_options)
                options["theta_start"] = start
                print(f"Refining {crop} {layers[0]} + sea from the sea fit", flush=True)
                retry = run_crop_experiments(crop, (layers,), method, options)[0]["fit_result"]
                retry_theta = np.asarray(retry.x, dtype=float)
                retry_error = float(retry.fun)
                if retry_theta.shape != (3,) or not np.all(np.isfinite(retry_theta)) or not np.isfinite(retry_error):
                    raise ValueError(f"Invalid warm-start fit for {crop}, {layers}.")
                if retry_error < squared_error:
                    theta, squared_error = retry_theta, retry_error
        refined.append((crop, layers, theta, squared_error))
    return refined


def select_nested_baselines(rows):
    """Keep a simpler fitted model when its zero-coefficient extension scores better."""
    selected = []
    average_by_crop = {}
    sea_by_crop = {}
    for crop, layers, theta, squared_error in rows:
        if not layers:
            average_by_crop[crop] = (theta, squared_error)
        elif layers == ("sea",):
            average_theta, average_error = average_by_crop[crop]
            if average_error < squared_error:
                theta = np.array([average_theta[0], 0.0])
                squared_error = average_error
            sea_by_crop[crop] = (theta, squared_error)
        else:
            sea_theta, sea_error = sea_by_crop[crop]
            if sea_error < squared_error:
                # Every combined model lists its environmental layer before sea.
                theta = np.array([sea_theta[0], 0.0, sea_theta[1]])
                squared_error = sea_error
        selected.append((crop, layers, theta, squared_error))
    return selected


def format_table(rows, method, dt, delta, apply_w, n_reps, seed, theta_limit, sweep_points):
    """Make a readable table with theta coefficients in listed layer order."""
    details = (f"Solver: `{method}`; delta: {delta:g}°; dt: {dt:g} years; "
               f"W: {apply_w}; theta bounds: [{-theta_limit:g}, {theta_limit:g}].")
    if method == "monte_carlo":
        details += f" Repetitions: {n_reps}; seed: {seed}."
    details += f" Initial sweep: {sweep_points} points per coefficient."
    lines = [
        "# Crop and layer experiment results",
        "",
        details,
        "Theta values are listed as intercept, then coefficients for the named layers. "
        "Values come from projected gradient descent after a coarse theta sweep; "
        "a nested simpler fit is kept if it scores better. A global optimum is not guaranteed.",
        "",
        "| Crop | Layers | Best theta (fit) | Best squared error (years²) |",
        "| --- | --- | --- | ---: |",
    ]
    for crop, layers, theta, squared_error in rows:
        layer_label = "average only" if not layers else " + ".join(layers)
        theta_label = ", ".join(f"{value:.10g}" for value in theta)
        lines.append(f"| {crop} | {layer_label} | {theta_label} | {squared_error:,.3f} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=("fast_marching", "monte_carlo"), default="fast_marching")
    parser.add_argument("--delta", type=float, default=0.5)
    parser.add_argument("--dt", type=float, default=40.0)
    parser.add_argument("--n-reps", type=int, default=100, help="Monte Carlo repetitions")
    parser.add_argument("--seed", type=int, default=12, help="Monte Carlo random seed")
    parser.add_argument("--theta-limit", type=float, default=5.0,
                        help="Absolute bound for every theta coefficient")
    parser.add_argument("--sweep-points", type=int, default=3,
                        help="Grid points per theta coefficient for starting-point sweep")
    parser.add_argument("--no-w", action="store_true", help="Disable cosine-latitude weighting")
    parser.add_argument(
        "--output", type=Path, default=Path("results/crop_layer_experiments.md")
    )
    args = parser.parse_args(argv)
    if not np.isfinite(args.theta_limit) or args.theta_limit <= 0:
        parser.error("--theta-limit must be a positive finite number")
    if args.sweep_points < 1:
        parser.error("--sweep-points must be a positive integer")
    options = {
        "delta": args.delta,
        "dt": args.dt,
        "n_reps": args.n_reps,
        "random_state": args.seed,
        "apply_w": not args.no_w,
        "theta_bounds": (-args.theta_limit, args.theta_limit),
    }
    rows = collect_results(CROPS, args.method, options, args.sweep_points, args.theta_limit)
    rows = select_nested_baselines(refine_from_sea(rows, args.method, options))
    table = format_table(rows, args.method, args.dt, args.delta, not args.no_w,
                         args.n_reps, args.seed, args.theta_limit, args.sweep_points)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(table, encoding="utf-8")
    print(f"Saved {len(rows)} results to {args.output}", flush=True)


if __name__ == "__main__":
    main()
