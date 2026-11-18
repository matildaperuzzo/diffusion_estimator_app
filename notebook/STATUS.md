# Status

Updated: 2026-11-18 10:08 +00:00 (Europe/London).

## Current state

- Git review found an origin-unknown replacement of the 18-row results table with Monte Carlo, 20 repetitions, seed 12, and 11 sweep points, plus a changed wheat notebook example and crop-table test expectation. The table was not regenerated or scientifically interpreted in this review.

- Added `run_experiments.py` for one user-selected crop and ordered layer set, with the existing solver and sweep options. Its `--extra-steps` option specifies Monte Carlo frames beyond the last observed frame; omitting it retains the 1,000-year extension. An intervening edit of unknown origin changed this script's default sweep count from 3 to 11; it was preserved. No fit was run; the current Python environment lacks `h5py`.

- `fit_theta` now uses one raw MSE per objective call and a centered 0.05-step gradient (six extra MSE calls for three coefficients), with no explicit Hessian. SLSQP supports optional bounds. Thirteen focused tests passed; a separate externally modified crop-table test expects 11 sweep points versus the script's default 3.

- `fit_theta` now minimizes MATLAB's locally averaged objective using SciPy trust-constr with finite-difference gradient and Hessian; raw and smoothed errors are saved separately. Fifteen focused tests passed, including bounded and unbounded fits. A full maize fit has not been rerun.

- Latest local maize/sea fit stopped after one iteration at sweep corner `[-2, 5]` with `line_search_failed`; the intercept is inside its optimizer bound. Python descent on raw MSE differs from MATLAB's unbounded trust-region fit on a locally averaged objective. No code change was made during diagnosis.

- The notebook/plot MSE difference at wheat/sea theta `[-1.6, 5]` was traced to solver settings: Monte Carlo (10 repetitions, seed 3) versus the plot script's fast-marching default. Current evaluations reproduced `2,341,702.819383` and `1,529,409.259322` years squared respectively.

- Added `tests/plot_objective_function.py` for a crop plus one layer; a coarse wheat/sea fast-marching smoke run saved an ignored plot in `generated_data/`. Existing `tests/layer_inspection.ipynb` changes are of unknown origin and were not touched.

- MATLAB `parameters.T` is now derived automatically from crop observation years and `dt`, following `bottlenecks/src/data_prep.m`; unreached Python arrivals use T−1 for zero-based indexing. Fifteen relevant tests passed.

- Python Monte Carlo now accepts MATLAB frame horizon `T`, counts unreached cells at `T`, and defaults to seed 12. NumPy and MATLAB Threefry streams still differ. Fourteen relevant tests passed; no crop fit was rerun.

- MATLAB/Python fitting paths compared by code review on 2026-11-12; ranked possible differences are unverified. An external, origin-unknown Git change moved tracked `run_model.m` to untracked `matlab_comparison_scripts/` alongside `fit_model.m`.

- Repository reviewed on 2026-11-12; no code or tests changed. Existing working-tree modifications remain unstaged and of unverified origin for this session.
- Shared `ProjectNotebooks/INDEX.md` sync is pending because that directory is outside this session's writable workspace.

- [Layer inspection](../tests/layer_inspection.ipynb) was moved into `tests/` by an external change; its wheat MATLAB/Python comparison cells remain intact.
- The [development log](DEVELOPMENT_LOG.md) now includes one five-layer comparison figure. Controlled 10-year climate sampling closes only 7.4% of the precipitation MSE gap and slightly worsens temperature MSE. The earlier attribution of the gap primarily to 100-year sampling is corrected. The user confirmed that Python's hydro file handling is acceptable.
- A read-only normalization check confirms the app standardizes each full global climate mean map to mean 0 and standard deviation 1 before cropping. The wheat-region precipitation and temperature maps have different moments; details are in the development log.
- [Experiment runners](../diffusion_estimator.py) fit one crop/layer model or a list of layer sets with optional theta sweep. Each `run_experiment` call now saves a versioned [optimizer result](../optimization_result.py) as JSON in `generated_data/`, with effective inputs, outputs, stopping status, and provenance. Six focused runner tests and three crop/layer table tests passed; a real wheat intercept-only fast-marching fit saved and reloaded its result.
- [Crop/layer experiment script](../run_crop_layer_experiments.py) has produced a [table of 18 fitted models](../results/crop_layer_experiments.md) for wheat, rice, and maize with the requested six layer sets. Its uncommitted, origin-unknown default method change sets Monte Carlo; values in the existing table are earlier local fits.
- [README.md](../README.md) now describes the estimator API and how to run single, batch, and prepared crop experiments.
- Git branch `main`, HEAD `4bf607126279c7efdef2cd0a955b4f6a20e7a498` (`added readme`, 2026-11-02 10:23 +00:00; external commit detected). `run_crop_layer_experiments.py` has an uncommitted change of unknown origin setting the default method to Monte Carlo; Codex did not modify it.
- `fit_theta` returns a serializable result while preserving `.x`, `.fun`, and `.nit` access. Its success flag now reflects the actual termination reason. Generated JSON files are ignored by Git; notebook and code changes remain unstaged.
- The application loads standardized HDF5 crop and environmental layers and provides fast-marching and Monte Carlo arrival-time methods. Source and processing details: [DATA_PROCESSING.md](../processing/DATA_PROCESSING.md).
- No approved scientific findings are recorded. The comparison and crop-fit table remain exploratory.

## Open tasks

- Climate normalization, interpolation, and time-window contributions remain to be isolated individually. The hydro/sea residual solver gap was not revisited.

## Next step

- Keep the Python hydro loader as is. Further climate processing comparisons can isolate normalization, interpolation, and window effects if requested.
