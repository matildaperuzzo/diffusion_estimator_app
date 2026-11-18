"""Fit one chosen crop/layer model and write a Markdown result.

Example: python run_experiments.py --crop wheat --layers prec sea
Use --layers without names for an intercept-only model.
"""

import argparse
import math
from pathlib import Path


CROPS = ("wheat", "rice", "maize")
LAYERS = ("sea", "prec", "tmean", "csi", "hydro")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crop", required=True, choices=CROPS, help="Crop to fit")
    parser.add_argument("--layers", required=True, nargs="*", choices=LAYERS,
                        metavar="LAYER", help="Layers in coefficient order (sea, prec, tmean, csi, hydro); give no names for intercept only")
    parser.add_argument("--method", choices=("fast_marching", "monte_carlo"), default="monte_carlo")
    parser.add_argument("--delta", type=float, default=0.5, help="Grid spacing in degrees (default: 0.5)")
    parser.add_argument("--dt", type=float, default=40.0, help="Time step in years (default: 40)")
    parser.add_argument("--n-reps", type=int, default=100, help="Monte Carlo repetitions (default: 100)")
    parser.add_argument("--seed", type=int, default=12, help="Monte Carlo random seed (default: 12)")
    parser.add_argument("--extra-steps", type=int,
                        help="Monte Carlo steps after the last observation (default: 1000-year extension)")
    parser.add_argument("--theta-limit", type=float, default=5.0,
                        help="Absolute bound for every theta coefficient (default: 5)")
    parser.add_argument("--sweep-points", type=int, default=11,
                        help="Grid points per coefficient in starting sweep (default: 11)")
    parser.add_argument("--no-w", action="store_true", help="Disable cosine-latitude weighting")
    parser.add_argument("--output", type=Path,
                        help="Markdown path (default: results/<crop>_<layers>_experiment.md)")
    args = parser.parse_args(argv)

    if len(set(args.layers)) != len(args.layers):
        parser.error("--layers must not contain duplicates")
    if not math.isfinite(args.theta_limit) or args.theta_limit <= 0:
        parser.error("--theta-limit must be a positive finite number")
    if args.sweep_points < 1:
        parser.error("--sweep-points must be a positive integer")
    if args.extra_steps is not None and args.extra_steps < 0:
        parser.error("--extra-steps must be a non-negative integer")

    # Import the model only after parsing, so --help works without model dependencies.
    from diffusion_estimator import run_experiment

    limits = [min(args.theta_limit, 2.0)] + [args.theta_limit] * len(args.layers)
    options = {
        "delta": args.delta,
        "dt": args.dt,
        "n_reps": args.n_reps,
        "random_state": args.seed,
        "apply_w": not args.no_w,
        "theta_bounds": (-args.theta_limit, args.theta_limit),
        "theta_range": [[-value for value in limits], limits],
        "num_points": args.sweep_points,
    }
    if args.extra_steps is not None:
        options["extra_steps"] = args.extra_steps
    experiment = run_experiment(args.crop, args.layers, args.method, options)
    fit = experiment["fit_result"]
    layer_label = " + ".join(args.layers) if args.layers else "average only"
    theta_label = ", ".join(f"{value:.10g}" for value in fit.x)
    output = args.output or Path("results") / (
        f"{args.crop}_{'_'.join(args.layers) if args.layers else 'average'}_experiment.md"
    )
    lines = [
        "# Crop and layer experiment result", "",
        f"Solver: `{args.method}`; delta: {args.delta:g}°; dt: {args.dt:g} years; "
        f"W: {not args.no_w}; theta bounds: [{-args.theta_limit:g}, {args.theta_limit:g}].",
        f"Initial sweep: {args.sweep_points} points per coefficient.",
        "Theta is the intercept followed by coefficients in the listed layer order. "
        "The fit is local; a global optimum is not guaranteed.", "",
        "| Crop | Layers | Fitted theta | Squared error (years²) |",
        "| --- | --- | --- | ---: |",
        f"| {args.crop} | {layer_label} | {theta_label} | {fit.fun:,.3f} |", "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved result to {output}")
    print(f"Saved optimizer record to {experiment['result_path']}")


if __name__ == "__main__":
    main()
