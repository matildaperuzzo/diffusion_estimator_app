"""Check source-variable selection when rebuilding sea and precipitation layers."""

# Use small classic NetCDF fixtures so the tests need no external source files.
from contextlib import contextmanager
from pathlib import Path
import unittest
from uuid import uuid4

import h5py
import numpy as np
from scipy.io import netcdf_file

from processing.rebuild_sea_prec import rebuild_precipitation, rebuild_sea


# Keep temporary NetCDF fixtures in the workspace so sandboxed test runs can write them.
TEST_DIRECTORY = Path(__file__).resolve().parent


@contextmanager
def fixture_directory():
    """Create a writable fixture directory and remove only its flat test files."""
    # Windows restricts tempfile's mode-0700 directories under this workspace.
    directory = TEST_DIRECTORY / f"fixture-{uuid4().hex}"
    directory.mkdir()
    try:
        yield directory
    finally:
        # Verify the generated location before cleaning up files from this test.
        if directory.resolve().parent != TEST_DIRECTORY:
            raise RuntimeError(f"Refusing to clean up outside the test directory: {directory}")
        for child in directory.iterdir():
            if not child.is_file():
                raise RuntimeError(f"Unexpected non-file fixture artifact: {child}")
            child.unlink()
        directory.rmdir()


class RebuildSeaPrecipitationTests(unittest.TestCase):
    """Exercise the source values and ordering that previously differed from MATLAB."""

    def test_sea_classifies_raw_missing_sentinel_before_masking(self) -> None:
        """Keep SAGE's large missing value as a sea cell after axis sorting."""
        # Place the sentinel, threshold boundary, and ordinary sea in unsorted axes.
        with fixture_directory() as directory:
            source = directory / "sage.nc"
            target = directory / "sea.h5"
            with netcdf_file(source, "w") as netcdf:
                netcdf.createDimension("time", 1)
                netcdf.createDimension("level", 1)
                netcdf.createDimension("latitude", 2)
                netcdf.createDimension("longitude", 3)
                netcdf.createVariable("latitude", "d", ("latitude",))[:] = [0.25, -0.25]
                netcdf.createVariable("longitude", "d", ("longitude",))[:] = [1.25, -0.75, 0.25]
                values = netcdf.createVariable(
                    "data", "f", ("time", "level", "latitude", "longitude")
                )
                values.missing_value = np.float32(9e20)
                values[:] = np.array([[[[0.0, 9e20, 100.0], [101.0, 42.0, 0.0]]]], dtype=np.float32)

            # The raw 9e20 cell must survive classification as sea, including when sorted.
            rebuild_sea(source, target)
            with h5py.File(target, "r") as output:
                np.testing.assert_array_equal(output["lat"][:], [-0.25, 0.25])
                np.testing.assert_array_equal(output["lon"][:], [-0.75, 0.25, 1.25])
                np.testing.assert_array_equal(output["data"][:], [[0, 0, 1], [1, 0, 0]])
                self.assertEqual(output["data"].dtype, np.dtype("uint8"))
                self.assertEqual(output.attrs["sea_threshold"], 100.0)

    def test_precipitation_selects_precc_and_every_tenth_frame(self) -> None:
        """Keep PRECC on its native grid with the app's 100-year sampling."""
        # Give PRECT a distinct value and encode time and source indices in PRECC.
        with fixture_directory() as directory:
            source = directory / "trace.nc"
            target = directory / "prec.h5"
            with netcdf_file(source, "w") as netcdf:
                netcdf.createDimension("time", 21)
                netcdf.createDimension("lat", 2)
                netcdf.createDimension("lon", 4)
                netcdf.createVariable("time", "d", ("time",))[:] = -22.0 + np.arange(21) / 100.0
                netcdf.createVariable("lat", "d", ("lat",))[:] = [10.0, -10.0]
                netcdf.createVariable("lon", "d", ("lon",))[:] = [0.0, 270.0, 90.0, 180.0]
                netcdf.createVariable("PRECT", "f", ("time", "lat", "lon"))[:] = -999.0
                precc = netcdf.createVariable("PRECC", "f", ("time", "lat", "lon"))
                frames = (
                    1000.0 * np.arange(21)[:, None, None]
                    + 100.0 * np.arange(2)[None, :, None]
                    + np.arange(4)[None, None, :]
                )
                precc[:] = frames.astype(np.float32)

            # The three output frames must come from PRECC at source indices 0, 10, 20.
            rebuild_precipitation(source, target)
            with h5py.File(target, "r") as output:
                np.testing.assert_array_equal(output["lat"][:], [-10.0, 10.0])
                np.testing.assert_array_equal(output["lon"][:], [-180.0, -90.0, 0.0, 90.0])
                np.testing.assert_allclose(output["time"][:], [-20050.0, -19950.0, -19850.0])
                self.assertEqual(output["data"].shape, (3, 2, 4))
                for output_index, source_index in enumerate((0, 10, 20)):
                    expected = np.array(
                        [[103, 101, 100, 102], [3, 1, 0, 2]], dtype=np.float32
                    ) + 1000.0 * source_index
                    np.testing.assert_array_equal(output["data"][output_index], expected)
                self.assertEqual(output.attrs["source_variable"], "PRECC")
                self.assertEqual(output.attrs["sample_step"], 10)
                self.assertEqual(output.attrs["sample_years"], 100)


if __name__ == "__main__":
    # Run this module directly as well as through unittest discovery.
    unittest.main()
