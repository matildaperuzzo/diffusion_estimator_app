"""Plot the sampled two-parameter objective for one crop and one layer.

Example:
    python tests/plot_objective_function.py wheat sea --points 21
"""

import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diffusion_estimator import DiffusionEstimator


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop", choices=("wheat", "rice", "maize"))
    parser.add_argument("layer", choices=("sea", "prec", "tmean", "csi", "hydro"))
    parser.add_argument("--method", choices=("fast_marching", "monte_carlo"),
                        default="fast_marching")
    parser.add_argument("--intercept-min", type=float, default=-2.0)
    parser.add_argument("--intercept-max", type=float, default=2.0)
    parser.add_argument("--layer-min", type=float, default=-5.0)
    parser.add_argument("--layer-max", type=float, default=5.0)
    parser.add_argument("--points", type=int, default=21,
                        help="samples along each coefficient axis")
    parser.add_argument("--delta", type=float, default=0.5)
    parser.add_argument("--dt", type=float, default=40.0)
    parser.add_argument("--n-reps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--time-horizon", type=int,
                        help="override the MATLAB-style horizon for Monte Carlo")
    parser.add_argument("--no-w", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.points < 2:
        parser.error("--points must be at least 2")
    if not all(map(np.isfinite, (args.intercept_min, args.intercept_max,
                               args.layer_min, args.layer_max))):
        parser.error("coefficient ranges must be finite")
    if args.intercept_min >= args.intercept_max or args.layer_min >= args.layer_max:
        parser.error("each coefficient minimum must be below its maximum")
    if args.n_reps < 1:
        parser.error("--n-reps must be positive")
    if args.time_horizon is not None and args.time_horizon < 1:
        parser.error("--time-horizon must be positive")
    return args


def main(argv=None):
    args = parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    estimator = DiffusionEstimator(args.crop, [args.layer], dt=args.dt, delta=args.delta)
    bounds = np.array([[args.intercept_min, args.layer_min],
                       [args.intercept_max, args.layer_max]])
    estimator.sweep_theta(
        bounds, args.points, method=args.method, n_reps=args.n_reps,
        random_state=args.seed, apply_w=not args.no_w,
        time_horizon=args.time_horizon,
    )
    intercepts = np.linspace(args.intercept_min, args.intercept_max, args.points)
    coefficients = np.linspace(args.layer_min, args.layer_max, args.points)
    errors = np.full((args.points, args.points), np.nan)
    for intercept, coefficient, error in estimator.objective_function:
        row = np.argmin(abs(coefficients - coefficient))
        column = np.argmin(abs(intercepts - intercept))
        errors[row, column] = error
    if not np.isfinite(errors).any():
        raise ValueError("No finite objective values were found in the requested range.")
    best_row, best_column = np.unravel_index(np.nanargmin(errors), errors.shape)
    best_theta = np.array([intercepts[best_column], coefficients[best_row]])
    best_error = errors[best_row, best_column]

    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.pcolormesh(intercepts, coefficients, np.ma.masked_invalid(errors),
                          shading="auto", cmap="viridis")
    fig.colorbar(image, ax=ax, label="Mean squared arrival-time error (years²)")
    ax.plot(best_theta[0], best_theta[1], "r*", markersize=12,
            label=f"Lowest sampled error: {best_error:,.0f} years²")
    ax.set(xlabel="Intercept coefficient", ylabel=f"{args.layer} coefficient",
           title=f"{args.crop.title()} + {args.layer}: {args.method} objective")
    ax.legend(loc="best")
    fig.tight_layout()
    output = args.output or Path("generated_data") / f"objective_{args.crop}_{args.layer}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)
    print(f"Saved {output} (best theta={best_theta}, MSE={best_error:.6f} years²)")


if __name__ == "__main__":
    main()
