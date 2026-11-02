# Status

Updated: 2026-11-02 09:19 +00:00 (Europe/London).

## Current state

- [Layer inspection](../tests/layer_inspection.ipynb) was moved into `tests/` by an external change; its wheat MATLAB/Python comparison cells remain intact.
- The [development log](DEVELOPMENT_LOG.md) now includes one five-layer comparison figure. Controlled 10-year climate sampling closes only 7.4% of the precipitation MSE gap and slightly worsens temperature MSE. The earlier attribution of the gap primarily to 100-year sampling is corrected. The user confirmed that Python's hydro file handling is acceptable.
- A read-only normalization check confirms the app standardizes each full global climate mean map to mean 0 and standard deviation 1 before cropping. The wheat-region precipitation and temperature maps have different moments; details are in the development log.
- [Experiment runners](../diffusion_estimator.py) fit one crop/layer model or a list of layer sets with optional theta sweep. Five focused tests and a real wheat/sea data-load smoke check passed.
- [Crop/layer experiment script](../run_crop_layer_experiments.py) has produced a [table of 18 fitted models](../results/crop_layer_experiments.md) for wheat, rice, and maize with the requested six layer sets. Three focused table tests passed. The default run uses fast marching and bounded theta; values are local fitted results.
- [README.md](../README.md) now describes the estimator API and how to run single, batch, and prepared crop experiments.
- Git branch `main`, HEAD `0984299b8cad8d64473615db45c4918ae9f513ee` (2026-10-28 commit of unknown origin, detected this session). The working tree was clean before the README and project-notebook edits.
- The application loads standardized HDF5 crop and environmental layers and provides fast-marching and Monte Carlo arrival-time methods. Source and processing details: [DATA_PROCESSING.md](../processing/DATA_PROCESSING.md).
- No approved scientific findings are recorded. The comparison and crop-fit table remain exploratory.

## Open tasks

- Climate normalization, interpolation, and time-window contributions remain to be isolated individually. The hydro/sea residual solver gap was not revisited.

## Next step

- Keep the Python hydro loader as is. Further climate processing comparisons can isolate normalization, interpolation, and window effects if requested.
