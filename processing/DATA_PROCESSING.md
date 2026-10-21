# Geography and TraCE data processing

The app loads standardized HDF5 files. The raw NetCDF sources remain in the
`bottlenecks` project. Use `processing/rebuild_sea_prec.py` to regenerate the
app's sea and precipitation files; the other conversion scripts remain in
`bottlenecks/python/convert_layers_to_hdf5.py`.

## App layout

- `processing/load_layers.py`: environmental layer loading and processing.
- `processing/load_data.py`: crop observation loading.
- `data/processed/layers/`: `csidata.h5`, `acc.h5`, `hmidata.h5`, `sea.h5`,
  `temp.h5`, `prec.h5`, and the legacy `W.h5`.
- `data/processed/crop/`: `wheat.h5`, `rice.h5`, and `maize.h5`.
- `layer_inspection.ipynb`: crop observations over a processed environmental layer.

Both loaders resolve their default data directories from their module locations,
independently of the working directory. A custom relative directory is resolved
from the caller's working directory. The estimator's optional `data_directory`
points to the parent containing both `crop/` and `layers/`.

## HDF5 sources

Each environmental file contains `lat`, `lon`, and `data`. Static rasters use
latitude-by-longitude order. Climate files additionally contain `time`, and their
data uses time-by-latitude-by-longitude order.

| Layer | Source and saved representation |
| --- | --- |
| `acc` | HydroSHEDS BIL tiles merged by maximum on the native 30-arc-second global grid; raw integer counts and zero-filled uncovered cells. |
| `csidata` | `pre1500OptCalories.tif`, padded to the global grid and saved unnormalized at 1/12 degree. |
| `hmidata` | Native `HMISea10.tif` pixels with geographic coordinates derived from its equal-area projection. |
| `sea` | Native 0.5-degree SAGE mask, classified from raw source values greater than 100, including the source's missing-value sentinel as MATLAB does. |
| `temp` | Original TraCE temperature grid, with every tenth timestep retained and no normalization during conversion. |
| `prec` | Original TraCE `PRECC` grid, with every tenth timestep retained and no normalization during conversion. MATLAB's precipitation layer also reads `PRECC`; `PRECT` is a different variable in the same NetCDF file. |
| `W` | Legacy raster extracted from `geography_0p5deg.mat`, retaining its stored resolution. |

The climate sources are `TraCE-21K-II.ann.TS.nc` and
`TraCE-21K-II.ann.PRECT.nc`. Retaining every tenth 10-year timestep gives
100-year spacing. This is decimation, not an average of ten source timesteps.
The precipitation file uses `PRECC` from the latter source, rather than its
`PRECT` variable.

Both saved climate time axes use calendar years. Precipitation conversion uses
`1950 + 1000 * source_time`, matching the existing temperature file's time
axis exactly. The app stores raw climate values so callers can choose a time
window and a spatial resolution independently.

## Processing at load time

`delta` is in degrees and defaults to `0.5`. It defines global pixel-center axes
and must divide both 180 and 360 degrees. Spatial cropping happens after
resampling and normalization, so changing the crop extent does not change
the normalization statistics.

For `temp` and `prec`, the order is:

1. Select the inclusive `year_extent`, or all stored years if it is omitted.
2. Average those years on the original NetCDF spatial grid.
3. Interpolate the average onto the global grid at the requested `delta`.
4. Normalize the finite global values to mean zero and population standard
   deviation one; non-finite cells remain non-finite.
5. Crop to the requested latitude and longitude extents.

For static continuous layers, the order is:

1. Resample the full layer to the requested `delta`.
2. Clip negative CSI/HMI values to zero.
3. Normalize using global non-sea cells and sample standard deviation
   (`ddof=1`), then set sea cells to zero.
4. Crop to the requested spatial extent.

ACC uses Pillow bilinear resizing with antialiasing during downsampling.
Longitude is resized in row blocks, followed by latitude, to limit memory use.
The source tiles have already been merged in the converter. CSI uses Pillow
bicubic resizing. HMI uses cubic interpolation in its georeferenced pixel
coordinates. ACC/HMI missing or uncovered values are filled with zero before
land normalization. CSI requires finite land values.

The sea mask uses nearest-neighbor sampling and is not normalized. `W` retains
its stored resolution and values; it is not covered by the variable-resolution
continuous-layer pipeline.

This app processing intentionally retains 100-year climate sampling, linear
spatial interpolation, and normalization of the selected mean map. MATLAB's
saved geography uses 10-year frames, spline interpolation, and normalization
of the full space-time cube, so the sampled precipitation maps need not match
MATLAB exactly.

## Loading layers

Use canonical names with `load_layer`: `csidata`, `acc`, `hmidata`, `sea`,
`temp`, and `prec`. In particular, a duplicate file named `csi.h5` must not be
selected as `csi`: that name does not activate the CSI processing branch.

```python
# Import the app's layer loader and use its project-relative data directory.
from processing.load_layers import load_layer

# Resample and normalize globally, then return the selected region.
csi = load_layer("csidata", (15.0, 60.0), (-17.0, 65.0), delta=0.5)

# Average only the requested calendar years before resampling and normalization.
temperature = load_layer(
    "temp", (15.0, 60.0), (-17.0, 65.0),
    year_extent=(-1000.0, 1000.0), delta=0.5,
)
```

`year_extent` applies only to `temp` and `prec`. The returned object contains
`data`, `lat`, and `lon`; climate results also include the selected `years`.

## Crop observations and estimator grid

Each crop file contains aligned `lat`, `lon`, and calendar-year `time` vectors,
plus an `index` matrix with one-based latitude, longitude, and time indices.
It also contains `lat_extent`, `lon_extent`, `padding`, `delta`, `time_step`,
`start_time`, and `end_time`. Coordinate arrays and extents use degrees.
The stored extents already include the converter's padding (normally 5 degrees).
No raster or grid coordinate vectors are stored in a crop file.

Wheat combines Pinhasi SITE rows and De Souza records; rice uses the Cobo
workbook's S1 Table; maize combines the cleaned maize workbook with the earliest
per-location Zea mays records from p3k14c. The converter warns and removes records
with non-finite latitude, longitude, or time while keeping arrays aligned.

```python
# Load observation lists and their padded extents.
from processing.load_data import load_data
crop = load_data("wheat")

# Match the climate window and spatial resolution used by the inspection notebook.
from diffusion_estimator import DiffusionEstimator
estimator = DiffusionEstimator("wheat", ["csi", "hydro", "prec"], delta=0.5)
```

The estimator accepts historical aliases: `csi` maps to `csidata`, `hydro` to
`acc`, and `tmean` to `temp`. `hmidata` remains a separate layer.

The estimator and notebook use the crop's observed minimum and maximum calendar
years as the climate averaging window. All selected estimator layers receive
the same `delta`. The grid comes from the loaded layers, and observation
coordinates are remapped to the nearest cells on those axes. The estimator does
not reuse spatial indices saved for a different grid. A model with no selected
layers uses the sea mask's axes to define its grid.

Default estimator observations come from the crop HDF5 file. Their stored
40-year temporal bins are retained, converted to zero-based elapsed time, and
scaled into the estimator's `dt` units. The estimator exposes the original point
object as `crop_points` and the mapped numerical observations as `dataset`
(and `crop_data`). An explicit `dataset` override uses zero-based spatial
indices on the chosen model grid and one-based time indices in units of `dt`.

The legacy `buffer_size_rad` argument adds an optional extra buffer beyond the
stored padded extents. Only this extra buffer is converted from radians; the
stored extents remain in degrees.

## Regeneration and dependencies

Regenerate `sea.h5` and `prec.h5` from this app's root using the raw sources in
the `bottlenecks` project:

```powershell
# Rebuild both raw-source layers in data/processed/layers.
.\.venv\Scripts\python.exe -m processing.rebuild_sea_prec --sea-source "..\bottlenecks\data\raw\SAGE\land_suit\land_suit_0.50x0.50.nc" --prec-source "..\bottlenecks\data\raw\trace\TraCE-21K-II.ann.PRECT.nc"
```

The script replaces each generated file only after writing it completely.
Other layer conversion still runs in the original `bottlenecks` project.
Copy those HDF5 files into this app's `data/processed/layers/` and the crop
files into `data/processed/crop/`.

Loading requires `numpy`, `h5py`, `scipy`, and `Pillow`; notebook plotting also
requires `matplotlib`. Conversion additionally uses `netCDF4`, `pandas`,
`openpyxl`, and `xlrd`. The app's sea and precipitation rebuild script instead
uses `scipy.io.netcdf_file` and requires no `netCDF4` installation. No
normalization of stored source data is performed by moving files into the app.
