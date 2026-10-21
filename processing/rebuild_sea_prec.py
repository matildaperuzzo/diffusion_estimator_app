"""Rebuild the app's sea and precipitation HDF5 source layers."""

# Keep conversion separate from load-time resampling and normalization.
import argparse
import os
from pathlib import Path
import tempfile

import h5py
import numpy as np
from scipy.io import netcdf_file


# TraCE frames are ten years apart; match the temperature file's 100-year sampling.
SAMPLE_STEP = 10
SEA_THRESHOLD = 100.0


def _temporary_path(target: Path) -> Path:
    """Create a temporary HDF5 path beside its final destination."""
    # Keeping the temporary file in the same directory permits atomic replacement.
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.stem}-", suffix=".h5", dir=target.parent)
    os.close(descriptor)
    return Path(name)


def rebuild_sea(source: Path, target: Path) -> None:
    """Classify raw SAGE values as MATLAB does, retaining the native 0.5-degree grid."""
    # scipy's NetCDF reader exposes the raw missing-value sentinel; MATLAB counts it as sea.
    with netcdf_file(source, "r", mmap=False) as netcdf:
        raw = np.asarray(netcdf.variables["data"][0, 0, :, :], dtype=np.float32)
        latitude = np.asarray(netcdf.variables["latitude"][:], dtype=np.float64)
        longitude = np.asarray(netcdf.variables["longitude"][:], dtype=np.float64)

    # Sort both coordinate axes and carry the categorical mask with them.
    latitude_order = np.argsort(latitude)
    longitude_order = np.argsort(longitude)
    sea = (raw > SEA_THRESHOLD).astype(np.uint8)
    sea = sea[np.ix_(latitude_order, longitude_order)]
    latitude = latitude[latitude_order]
    longitude = longitude[longitude_order]

    # Write a complete replacement before publishing the generated asset.
    temporary = _temporary_path(target)
    try:
        with h5py.File(temporary, "w") as output:
            output.create_dataset("lat", data=latitude)
            output.create_dataset("lon", data=longitude)
            output.create_dataset("data", data=sea, compression="gzip", compression_opts=4, shuffle=True)
            output.attrs["source"] = str(source)
            output.attrs["source_delta"] = 0.5
            output.attrs["sea_threshold"] = SEA_THRESHOLD
            output.attrs["classification"] = "raw data > sea_threshold, including the source missing-value sentinel"
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def rebuild_precipitation(source: Path, target: Path) -> None:
    """Store unnormalized PRECC frames on their native grid every 100 years."""
    # Choose PRECC by name: MATLAB's precipitation layer reads NetCDF variable 1.
    with netcdf_file(source, "r", mmap=False) as netcdf:
        variable = netcdf.variables["PRECC"]
        source_latitude = np.asarray(netcdf.variables["lat"][:], dtype=np.float64)
        source_longitude = np.asarray(netcdf.variables["lon"][:], dtype=np.float64)
        source_time = np.asarray(netcdf.variables["time"][:], dtype=np.float64)
        sampled_indices = np.arange(0, source_time.size, SAMPLE_STEP, dtype=np.int64)

        # Convert ka BP to calendar years exactly as the existing temp.h5 conversion does.
        calendar_years = 1950.0 + 1000.0 * source_time[sampled_indices]
        longitude = (source_longitude + 180.0) % 360.0 - 180.0
        latitude_order = np.argsort(source_latitude)
        longitude_order = np.argsort(longitude)
        latitude = source_latitude[latitude_order]
        longitude = longitude[longitude_order]

        # Stream the selected frames, preserving the app's native-grid HDF5 format.
        temporary = _temporary_path(target)
        try:
            with h5py.File(temporary, "w") as output:
                output.create_dataset("lat", data=latitude)
                output.create_dataset("lon", data=longitude)
                output.create_dataset("time", data=calendar_years)
                data = output.create_dataset(
                    "data",
                    shape=(sampled_indices.size, latitude.size, longitude.size),
                    dtype="f4",
                    chunks=(1, latitude.size, longitude.size),
                    compression="gzip",
                    compression_opts=4,
                    shuffle=True,
                )
                for output_index, source_index in enumerate(sampled_indices):
                    frame = np.asarray(variable[int(source_index), :, :], dtype=np.float32)
                    data[output_index] = frame[np.ix_(latitude_order, longitude_order)]
                output.attrs["source"] = str(source)
                output.attrs["source_variable"] = "PRECC"
                output.attrs["sample_step"] = SAMPLE_STEP
                output.attrs["sample_years"] = 100
                output.attrs["normalization"] = "at load time"
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> None:
    """Accept raw source locations and rebuild both app layer files."""
    # Raw NetCDF sources live outside this repository, so their paths are explicit.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sea-source", type=Path, required=True)
    parser.add_argument("--prec-source", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "processed" / "layers",
    )
    arguments = parser.parse_args()

    # Build the two independent assets in the app's standardized layer directory.
    rebuild_sea(arguments.sea_source, arguments.output_dir / "sea.h5")
    rebuild_precipitation(arguments.prec_source, arguments.output_dir / "prec.h5")


if __name__ == "__main__":
    # Run conversion only when this module is invoked as a script.
    main()
