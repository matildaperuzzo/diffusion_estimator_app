"""Load standardized geography layers and spatially averaged TraCE data."""

# Import path handling and HDF5-backed array access.
from pathlib import Path

import h5py
import numpy as np
from PIL import Image
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import map_coordinates


# Locate the moved layer files independently of the caller's working directory.
DEFAULT_LAYER_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "processed" / "layers"
TRACE_LAYERS = {"temp", "prec"}


def _extent_slice(coordinate: np.ndarray, extent: tuple[float, float]) -> slice:
    """Convert an inclusive coordinate extent into a contiguous HDF5 slice."""
    # Normalize extent ordering so callers may provide either endpoint first.
    lower, upper = sorted(extent)
    indices = np.flatnonzero((coordinate >= lower) & (coordinate <= upper))
    if len(indices) == 0:
        raise ValueError(f"Extent {extent} does not intersect the layer grid.")
    return slice(int(indices[0]), int(indices[-1]) + 1)


def _global_coordinates(delta: float) -> tuple[np.ndarray, np.ndarray]:
    """Build global pixel-center axes for a resolution that divides the globe."""
    # Require an integer number of cells along each global axis for consistent grids.
    latitude_count = round(180.0 / delta)
    longitude_count = round(360.0 / delta)
    if not np.isclose(latitude_count * delta, 180.0) or not np.isclose(longitude_count * delta, 360.0):
        raise ValueError("delta must divide both 180 degrees of latitude and 360 degrees of longitude.")
    # Return ascending latitude and longitude centers aligned with the global layers.
    latitude = -90.0 + delta / 2.0 + np.arange(latitude_count) * delta
    longitude = -180.0 + delta / 2.0 + np.arange(longitude_count) * delta
    return latitude, longitude


def _resize_image(data: np.ndarray, shape: tuple[int, int], resample: Image.Resampling) -> np.ndarray:
    """Resize a two-dimensional array with Pillow's selected interpolation filter."""
    # Avoid interpolation when the input already has the requested dimensions.
    if data.shape == shape:
        # Return an owned array because callers may clip or normalize it in place.
        return np.array(data, copy=True)
    # Pillow's floating-point image mode preserves CSI values through bicubic resizing.
    image = Image.fromarray(np.asarray(data, dtype=np.float32))
    resized = image.resize((shape[1], shape[0]), resample=resample)
    return np.asarray(resized, dtype=np.float32)


def _resample_to_grid(
    data: np.ndarray,
    source_latitude: np.ndarray,
    source_longitude: np.ndarray,
    target_latitude: np.ndarray,
    target_longitude: np.ndarray,
    method: str = "linear",
) -> np.ndarray:
    """Interpolate a latitude-by-longitude matrix onto target coordinates."""
    # Sort source axes and reorder the matrix for ascending-axis interpolation.
    latitude_order = np.argsort(source_latitude)
    longitude_order = np.argsort(source_longitude)
    ordered_data = np.take(np.take(data, latitude_order, axis=0), longitude_order, axis=1)
    ordered_latitude = source_latitude[latitude_order]
    ordered_longitude = source_longitude[longitude_order]
    # Extend nearest-neighbor categorical masks through the source cell edges.
    if method == "nearest":
        target_latitude = np.clip(target_latitude, ordered_latitude[0], ordered_latitude[-1])
        target_longitude = np.clip(target_longitude, ordered_longitude[0], ordered_longitude[-1])
    # Build target query points in latitude-longitude order for the interpolator.
    mesh_longitude, mesh_latitude = np.meshgrid(target_longitude, target_latitude)
    query_points = np.column_stack((mesh_latitude.ravel(), mesh_longitude.ravel()))
    # Apply coordinate-aware interpolation, including nearest sampling for masks.
    interpolator = RegularGridInterpolator(
        (ordered_latitude, ordered_longitude),
        ordered_data,
        method=method,
        bounds_error=False,
        fill_value=np.nan,
    )
    return interpolator(query_points).reshape(target_latitude.size, target_longitude.size)


def _resample_hmi_bicubic(
    data: np.ndarray,
    source_latitude: np.ndarray,
    source_longitude: np.ndarray,
    target_latitude: np.ndarray,
    target_longitude: np.ndarray,
) -> np.ndarray:
    """Resample georeferenced HMI pixels with bicubic interpolation on pixel coordinates."""
    # Convert each target coordinate to a fractional source row or column position.
    source_rows = np.interp(target_latitude, source_latitude, np.arange(source_latitude.size))
    source_columns = np.interp(target_longitude, source_longitude, np.arange(source_longitude.size))
    # Mark targets beyond source coverage so they become zero after resampling.
    outside_latitude = (target_latitude < source_latitude[0]) | (target_latitude > source_latitude[-1])
    outside_longitude = (target_longitude < source_longitude[0]) | (target_longitude > source_longitude[-1])
    # Evaluate a cubic spline in the source image while retaining its georeferenced axes.
    row_grid, column_grid = np.meshgrid(source_rows, source_columns, indexing="ij")
    sampled = map_coordinates(
        np.asarray(data, dtype=np.float32),
        (row_grid, column_grid),
        order=3,
        mode="nearest",
        prefilter=True,
    )
    sampled[outside_latitude, :] = np.nan
    sampled[:, outside_longitude] = np.nan
    return sampled


def _resample_acc_merged(
    source_data: h5py.Dataset,
    source_delta: float,
    target_latitude: np.ndarray,
    target_longitude: np.ndarray,
) -> np.ndarray:
    """Resize the merged native ACC raster with antialiased bilinear interpolation."""
    # Confirm that the stored axes cover a global raster at the recorded source resolution.
    expected_shape = (round(180.0 / source_delta), round(360.0 / source_delta))
    if source_data.shape != expected_shape:
        raise ValueError(
            f"ACC raster shape {source_data.shape} does not match source_delta={source_delta} "
            f"(expected {expected_shape})."
        )
    # Return the stored raster directly when its native and requested grids coincide.
    target_shape = (target_latitude.size, target_longitude.size)
    if source_data.shape == target_shape:
        native = np.asarray(source_data[:], dtype=np.float32)
        return np.nan_to_num(native, nan=0.0, posinf=0.0, neginf=0.0)
    # Resample longitude in row blocks so the multi-gigabyte native raster stays on disk.
    intermediate = np.empty((source_data.shape[0], target_longitude.size), dtype=np.float32)
    row_block_size = 128
    for first_row in range(0, source_data.shape[0], row_block_size):
        last_row = min(first_row + row_block_size, source_data.shape[0])
        # Treat gaps in older merged files as zero, matching MATLAB's post-merge fill.
        block = np.asarray(source_data[first_row:last_row, :], dtype=np.float32)
        np.nan_to_num(block, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        # Pillow widens its bilinear filter while shrinking, matching imresize antialiasing.
        image = Image.fromarray(block)
        resized = image.resize(
            (target_longitude.size, block.shape[0]),
            resample=Image.Resampling.BILINEAR,
        )
        intermediate[first_row:last_row, :] = np.asarray(resized, dtype=np.float32)
    # Apply the same separable bilinear resize on latitude after longitude is complete.
    image = Image.fromarray(intermediate)
    resized = image.resize(
        (target_longitude.size, target_latitude.size),
        resample=Image.Resampling.BILINEAR,
    )
    result = np.asarray(resized, dtype=np.float32)
    # MATLAB's imresize keeps the integer class of the original HydroSHEDS raster.
    if np.issubdtype(source_data.dtype, np.integer):
        result = np.floor(result + 0.5)
    return result


def _load_target_sea_mask(
    layer_directory: Path,
    target_latitude: np.ndarray,
    target_longitude: np.ndarray,
) -> np.ndarray:
    """Read and nearest-resample the native SAGE sea mask onto a requested global grid."""
    # Require the source mask because static land normalization depends on it.
    sea_path = Path(layer_directory) / "sea.h5"
    if not sea_path.exists():
        raise FileNotFoundError(f"Sea mask file required to normalize the layer is missing: {sea_path}")
    with h5py.File(sea_path, "r") as sea_source:
        sea = sea_source["data"][:].astype(np.uint8)
        sea_latitude = sea_source["lat"][:]
        sea_longitude = sea_source["lon"][:]
    # Use geographic nearest-neighbor sampling so the categorical mask stays categorical.
    return _resample_to_grid(
        sea,
        sea_latitude,
        sea_longitude,
        target_latitude,
        target_longitude,
        method="nearest",
    ).astype(bool)


def _normalize_land_values(data: np.ndarray, sea_mask: np.ndarray, layer_name: str) -> np.ndarray:
    """Normalize finite non-sea values and explicitly set sea cells to zero."""
    # Replace uncovered or missing layer cells with zero before selecting non-sea values.
    normalized = np.nan_to_num(np.asarray(data, dtype=np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    land_values = normalized[~sea_mask]
    if land_values.size == 0:
        raise ValueError(f"Layer {layer_name} has no non-sea values at the requested resolution.")
    # Match MATLAB's default sample standard deviation and fail on constant land data.
    mean = np.mean(land_values)
    standard_deviation = np.std(land_values, ddof=1)
    if not np.isfinite(mean) or not np.isfinite(standard_deviation) or standard_deviation == 0.0:
        raise ValueError(f"Layer {layer_name} has non-finite or constant non-sea values.")
    normalized = (normalized - mean) / standard_deviation
    normalized[sea_mask] = 0.0
    return normalized


def load_layer(
    layer_name: str,
    latitude_extent: tuple[float, float],
    longitude_extent: tuple[float, float],
    year_extent: tuple[float, float] | None = None,
    layer_directory: Path = DEFAULT_LAYER_DIRECTORY,
    delta: float = 0.5,
) -> dict[str, np.ndarray]:
    """Load one layer and return data with its selected coordinates.

    Trace layers are averaged across all years when ``year_extent`` is omitted,
    or across the inclusive requested year range when it is provided. Trace
    averages are resampled to ``delta`` degrees and normalized over their finite
    spatial values. Static continuous layers are resampled and normalized over
    non-sea cells before the requested spatial extent is applied.
    """
    # Validate the year-only argument before opening the requested layer.
    if year_extent is not None and layer_name not in TRACE_LAYERS:
        raise ValueError("year_extent only applies to temp and prec layers.")
    # Reject non-positive resolutions before calculating target grid coordinates.
    if delta <= 0.0:
        raise ValueError("delta must be positive.")
    path = Path(layer_directory) / f"{layer_name}.h5"
    if not path.exists():
        raise FileNotFoundError(f"No standardized layer file exists: {path}")
    with h5py.File(path, "r") as source:
        # Read high-resolution CSI globally so interpolation and normalization use the full layer.
        if layer_name == "csidata":
            if "source_delta" not in source.attrs:
                raise ValueError(f"CSI file {path} lacks native-resolution metadata; regenerate it from the source GeoTIFF.")
            source_delta = float(source.attrs["source_delta"])
            if delta < source_delta and not np.isclose(delta, source_delta):
                raise ValueError(f"delta={delta} would upsample CSI data finer than its {source_delta}-degree source.")
            target_latitude, target_longitude = _global_coordinates(delta)
            csi = source["data"][:]
            # Own the result because clipping and normalization below modify it in place.
            csi = np.array(
                _resize_image(csi, (target_latitude.size, target_longitude.size), Image.Resampling.BICUBIC),
                copy=True,
            )
            # Match build_geography.m by clipping negative values after the resolution change.
            csi[csi < 0.0] = 0.0
            # Read and geographically align the native SAGE sea mask to this target grid.
            sea_mask = _load_target_sea_mask(layer_directory, target_latitude, target_longitude)
            # Normalize land values after downsampling and restore sea cells to zero.
            land_values = csi[~sea_mask]
            if land_values.size == 0 or not np.all(np.isfinite(land_values)):
                raise ValueError("CSI has no finite land values at the requested resolution.")
            land_mean = np.mean(land_values)
            land_standard_deviation = np.std(land_values, ddof=1)
            if land_standard_deviation == 0.0:
                raise ValueError("CSI has zero variance over land at the requested resolution.")
            csi = (csi - land_mean) / land_standard_deviation
            csi[sea_mask] = 0.0
            latitude = target_latitude
            longitude = target_longitude
            data = csi
            selected_years = None
        elif layer_name in {"acc", "hmidata", "sea"}:
            # Resample source-derived ACC, HMI, or sea data globally before cropping.
            target_latitude, target_longitude = _global_coordinates(delta)
            if layer_name == "acc":
                # Resize the converter's already-merged native raster with MATLAB-like bilinear filtering.
                if "source_delta" not in source.attrs:
                    raise ValueError(f"ACC file {path} lacks native-resolution metadata; regenerate it from HydroSHEDS.")
                data = _resample_acc_merged(
                    source["data"],
                    float(source.attrs["source_delta"]),
                    target_latitude,
                    target_longitude,
                )
            elif layer_name == "hmidata":
                # Use the embedded GeoTIFF coordinates and bicubic pixel interpolation for HMI.
                latitude = source["lat"][:]
                longitude = source["lon"][:]
                data = _resample_hmi_bicubic(
                    source["data"][:], latitude, longitude, target_latitude, target_longitude
                )
            else:
                # Sea is categorical, so align it with nearest-neighbor sampling only.
                latitude = source["lat"][:]
                longitude = source["lon"][:]
                data = _resample_to_grid(
                    source["data"][:],
                    latitude,
                    longitude,
                    target_latitude,
                    target_longitude,
                    method="nearest",
                ).astype(bool)
            if layer_name == "hmidata":
                # Match build_geography.m by clipping negative HMI values after resampling.
                data[data < 0.0] = 0.0
            if layer_name in {"acc", "hmidata"}:
                # Normalize each continuous source over land and zero the sea before cropping.
                sea_mask = _load_target_sea_mask(layer_directory, target_latitude, target_longitude)
                data = _normalize_land_values(data, sea_mask, layer_name)
            latitude = target_latitude
            longitude = target_longitude
            selected_years = None
        else:
            # Other standardized layers retain the axes and resolution in their HDF5 files.
            latitude = source["lat"][:]
            longitude = source["lon"][:]
            if layer_name in TRACE_LAYERS:
                # Select the requested inclusive time range before averaging.
                years = source["time"][:]
                if year_extent is None:
                    time_slice = slice(None)
                else:
                    time_slice = _extent_slice(years, year_extent)
                # Average selected years over the full source grid before spatial resampling.
                averaged = np.nanmean(source["data"][time_slice, :, :], axis=0)
                target_latitude, target_longitude = _global_coordinates(delta)
                data = _resample_to_grid(
                    averaged,
                    latitude,
                    longitude,
                    target_latitude,
                    target_longitude,
                )
                # Normalize the complete resampled spatial matrix before applying spatial cropping.
                mean = np.nanmean(data)
                standard_deviation = np.nanstd(data)
                if not np.isfinite(mean) or not np.isfinite(standard_deviation) or standard_deviation == 0.0:
                    raise ValueError(
                        f"Trace layer {layer_name} has no finite values or zero variance in the selected years."
                    )
                data = (data - mean) / standard_deviation
                # Select the requested extent only after full-grid normalization.
                latitude = target_latitude
                longitude = target_longitude
                latitude_slice = _extent_slice(latitude, latitude_extent)
                longitude_slice = _extent_slice(longitude, longitude_extent)
                selected_latitude = latitude[latitude_slice]
                selected_longitude = longitude[longitude_slice]
                data = data[latitude_slice, longitude_slice]
                selected_years = years[time_slice]
            else:
                # Read non-trace static layers at their stored spatial resolution.
                latitude_slice = _extent_slice(latitude, latitude_extent)
                longitude_slice = _extent_slice(longitude, longitude_extent)
                selected_latitude = latitude[latitude_slice]
                selected_longitude = longitude[longitude_slice]
                data = source["data"][latitude_slice, longitude_slice]
                selected_years = None
    # Select the requested extent only after source resampling and normalization.
    if layer_name in {"csidata", "acc", "hmidata", "sea"}:
        latitude_slice = _extent_slice(latitude, latitude_extent)
        longitude_slice = _extent_slice(longitude, longitude_extent)
        selected_latitude = latitude[latitude_slice]
        selected_longitude = longitude[longitude_slice]
        data = data[latitude_slice, longitude_slice]
    result = {"data": np.asarray(data), "lat": selected_latitude, "lon": selected_longitude}
    if selected_years is not None:
        result["years"] = selected_years
    return result
