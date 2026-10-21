"""Fit a crop/layer diffusion model and save labelled arrival-time contours."""

# Import argparse so the crop, layers, and fit settings can be supplied at runtime.
import argparse
# Import pathlib for portable input and output paths.
from pathlib import Path
# Import sys so the script can find project modules when run from this subfolder.
import sys
# Import urllib helpers so Esri imagery can be downloaded without extra packages.
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Import matplotlib for creating and saving the contour figure.
import matplotlib.pyplot as plt
import matplotlib as mpl
# Draw observation images at a fixed display size and include the image in the legend.
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.legend_handler import HandlerBase
# Resize the display copy once so hundreds of markers do not each resample a full JPEG.
from PIL import Image
# Import numpy for parameter arrays and contour levels.
import numpy as np
from scipy.io import loadmat

# Add the repository root to the module search path for direct script execution.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Import the project estimator from the repository root.
from diffusion_estimator import DiffusionEstimator


def get_crop_extent(crop):
    """Load the crop bounding box as (minimum longitude, minimum latitude, maximum longitude, maximum latitude)."""
    # Load the crop-specific latitude and longitude extent file.
    extent_file = Path(__file__).resolve().parents[1] / "data" / f"{crop}_latlon.mat"
    extent_data = loadmat(extent_file)
    # Flatten MATLAB row vectors and validate that each extent has two values.
    latitudes = np.asarray(extent_data["lats"], dtype=float).ravel()
    longitudes = np.asarray(extent_data["lons"], dtype=float).ravel()
    if latitudes.size != 2 or longitudes.size != 2:
        raise ValueError(f"Expected two latitude and longitude bounds in {extent_file}.")
    # Return the bounds in the order expected by mapping and matplotlib APIs.
    return longitudes.min(), latitudes.min(), longitudes.max(), latitudes.max()


def download_esri_world_imagery(crop, extent, output_path, width=1600, height=1200):
    """Download an Esri World Imagery image for a crop extent and return its path."""
    # Use Esri's public export endpoint with a geographic WGS84 bounding box.
    service_url = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
    # Build an image request that preserves the requested territory bounds.
    query = urlencode({
        "bbox": ",".join(f"{value:.10f}" for value in extent),
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": f"{width},{height}",
        "format": "jpg",
        "f": "image",
    })
    # Identify the application when requesting imagery from the public service.
    request = Request(f"{service_url}?{query}", headers={"User-Agent": "diffusion-estimator-app/1.0"})
    # Download the returned JPEG and cache it so repeated plots do not re-download it.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=60) as response, output_path.open("wb") as image_file:
        image_file.write(response.read())
    return output_path


def format_arrival_year(elapsed_years, start_year):
    """Label elapsed years or a calendar arrival date when the origin is known."""
    # Without a stored source date, show elapsed time instead of inventing BC dates.
    if start_year is None:
        return f"{elapsed_years:,.0f} years"
    # Advance through historical years without introducing a year zero.
    astronomical_start = start_year + 1 if start_year < 0 else start_year
    arrival_year = int(np.floor(astronomical_start + elapsed_years + 0.5))
    return f"{1 - arrival_year:,} BC" if arrival_year <= 0 else f"{arrival_year:,} AD"


class ObservationImageHandler(HandlerBase):
    """Draw the observation image inside its legend entry."""

    def create_artists(self, legend, original_handle, xdescent, ydescent, width, height, fontsize, transform):
        # Fit the image to the legend's height while preserving its aspect ratio.
        marker = OffsetImage(original_handle.get_data(), zoom=height / original_handle.get_data().shape[0])
        artist = AnnotationBbox(marker, (width / 2 - xdescent, height / 2 - ydescent), xycoords=transform, frameon=False, pad=0)
        return [artist]


def add_observation_markers(axes, estimator, satellite, marker_path, marker_size):
    """Overlay a reproducible tenth of observations with image markers in points."""
    # Convert the provided JPEG into a display image with a transparent white background.
    with Image.open(marker_path) as source_image:
        display_image = source_image.convert("RGBA")
        # Use twice the exported pixel height for crisp edges at the plot's 200 dpi.
        display_height = max(1, int(np.ceil(marker_size * 200 / 72 * 2)))
        display_image.thumbnail((display_height, display_height), Image.Resampling.LANCZOS)
        marker_image = np.asarray(display_image, dtype=float) / 255.0
    rgb = marker_image[:, :, :3]
    # Fade near-white JPEG pixels to avoid rectangular patches and compression fringes.
    alpha = np.clip((1.0 - rgb.min(axis=2)) / 0.15, 0, 1) * marker_image[:, :, 3]
    marker_image = np.dstack((rgb, alpha))
    # Resolve grid indices using the same coordinates as the arrival-time field.
    observation_x = estimator.dataset[:, 1]
    observation_y = estimator.dataset[:, 0]
    if satellite:
        observation_x = np.interp(observation_x, np.arange(estimator.longitude.size), estimator.longitude)
        observation_y = np.interp(observation_y, np.arange(estimator.latitude.size), estimator.latitude)
        # Prefer the original unrounded site locations when MATLAB metadata retains them.
        metadata_path = Path(__file__).resolve().parents[1] / "data" / f"{estimator.crop}.mat"
        if metadata_path.exists():
            parameters = loadmat(metadata_path, squeeze_me=True, struct_as_record=False).get("parameters")
            if parameters is not None and hasattr(parameters, "dataset_lat") and hasattr(parameters, "dataset_lon"):
                original_latitude = np.asarray(parameters.dataset_lat).ravel()
                original_longitude = np.asarray(parameters.dataset_lon).ravel()
                if original_latitude.size == observation_y.size and original_longitude.size == observation_x.size:
                    observation_x, observation_y = original_longitude, original_latitude
    # Normalize by image height so marker size stays constant across resolutions and extents.
    zoom = marker_size / marker_image.shape[0]
    # Sample without replacement using a fixed seed so repeat plots show the same sites.
    sample_size = max(1, len(observation_x) // 10) if len(observation_x) else 0
    sample_indices = np.random.default_rng(0).choice(len(observation_x), size=sample_size, replace=False)
    for longitude, latitude in zip(observation_x[sample_indices], observation_y[sample_indices]):
        marker = OffsetImage(marker_image, zoom=zoom, interpolation="hanning")
        # Keep contours above observations and the highlighted source above both.
        artist = AnnotationBbox(marker, (longitude, latitude), frameon=False, pad=0, zorder=1.5, annotation_clip=True)
        artist.set_in_layout(False)
        axes.add_artist(artist)
    # Return an image handle so the legend uses the same marker as the observations.
    return OffsetImage(marker_image, zoom=zoom)


def make_arrival_time_plot(crop, layers, theta_start, theta_bounds, dt, output_path, satellite=False, satellite_alpha=0.65, start_year=None, contour_interval=1000.0, max_years=None, marker_image=None, marker_size=12.0):
    """Fit the selected model and save contours labelled in calendar years."""
    # Construct the estimator, which loads the crop's raw observations by default.
    estimator = DiffusionEstimator(crop=crop, layers=layers, dt=dt)
    # Recover the source date from original parameters when an override is absent.
    if start_year is None:
        metadata_path = Path(__file__).resolve().parents[1] / "data" / f"{crop}.mat"
        if metadata_path.exists():
            parameters = loadmat(metadata_path, squeeze_me=True, struct_as_record=False).get("parameters")
            if parameters is not None and hasattr(parameters, "start_time"):
                start_year = float(parameters.start_time)
    # Validate dates and spacing for both imported and command-line callers.
    if start_year is not None and (not np.isfinite(start_year) or start_year == 0):
        raise ValueError("start_year must be finite and nonzero (negative for BC, positive for AD).")
    if not np.isfinite(contour_interval) or contour_interval <= 0:
        raise ValueError("contour_interval must be finite and positive.")
    if max_years is not None and (not np.isfinite(max_years) or max_years <= 0):
        raise ValueError("max_years must be finite and positive.")
    # Validate marker settings before starting the model fit.
    if not np.isfinite(marker_size) or marker_size <= 0:
        raise ValueError("marker_size must be finite and positive.")
    marker_path = Path(marker_image) if marker_image is not None else Path(__file__).parent / "created_plots" / "wheat.jpg"
    if not marker_path.is_file():
        raise FileNotFoundError(f"Observation marker image does not exist: {marker_path}")
    # Fit one intercept parameter plus one coefficient for each selected layer.
    fit_result = estimator.fit_theta(theta_start=theta_start, theta_bounds=theta_bounds)
    # Recompute the speed and arrival-time field using the fitted coefficients.
    speed = estimator.build_speed(fit_result.x)
    # Use the estimator's actual coordinates so fitting and plotting solve the same field.
    geographic_extent = (estimator.longitude.min(), estimator.latitude.min(), estimator.longitude.max(), estimator.latitude.max()) if satellite else None
    arrival_steps = estimator.get_arrival_times(speed)
    # Convert fast-marching grid steps into years using the model time step.
    arrival_years = arrival_steps * dt
    # Show the observed period by default instead of all distant extrapolated arrivals.
    finite_years = arrival_years[np.isfinite(arrival_years)]
    observed_years = float(np.max(estimator.dataset[:, 2]) * dt)
    maximum_year = min(float(np.max(finite_years)), observed_years if max_years is None else max_years)
    # Keep at most twelve intervals, increasing spacing by whole requested intervals.
    contour_interval *= max(1, np.ceil(maximum_year / (12 * contour_interval)))
    contour_levels = np.arange(contour_interval, maximum_year + 1e-8, contour_interval)
    # Fail clearly if the selected data cannot produce even one requested contour.
    if contour_levels.size == 0:
        raise ValueError("The selected time range does not reach one contour interval; reduce --contour-interval.")

    # Create a coordinate grid whose indices match the fast-marching array.
    x_coordinates, y_coordinates = np.meshgrid(
        estimator.longitude if satellite else np.arange(arrival_years.shape[1]),
        # Each field row keeps its actual latitude; no flip or extent interpolation is needed.
        estimator.latitude if satellite else np.arange(arrival_years.shape[0]),
    )
    # Create a readable figure before optionally drawing the satellite background.
    figure, axes = plt.subplots(figsize=(8, 5))
    # Draw a user-supplied satellite image underneath the contours on the model grid.
    if satellite:
        # Cache the crop-specific imagery beside the generated plot.
        satellite_path = Path(__file__).parent / "created_plots" / f"{crop}_esri_world_imagery.jpg"
        # Download the image only when it is not already cached locally.
        if not satellite_path.exists():
            download_esri_world_imagery(crop, geographic_extent, satellite_path)
        # Read the downloaded satellite image and place it under the contours.
        satellite_image = plt.imread(satellite_path)
        axes.imshow(
            satellite_image,
            # Esri images are north-up, so the first image row belongs at maximum latitude.
            origin="upper",
            extent=(geographic_extent[0], geographic_extent[2], geographic_extent[1], geographic_extent[3]),
            alpha=satellite_alpha,
            aspect="auto",
            zorder=0,
        )
    # Draw one contour line for every 1,000-year arrival interval.
    contours = axes.contour(
        x_coordinates,
        y_coordinates,
        # Keep the arrival field in the same row order as the model coordinates.
        arrival_years,
        levels=contour_levels,
        cmap="YlOrBr_r",
        linewidths=1.25,
    )
    # Advance contour dates from the source rather than labelling elapsed time as BC.
    axes.clabel(
        contours,
        inline=True,
        fontsize=8,
        fmt=lambda value: format_arrival_year(value, start_year),
    )
    # Mark the model's starting point so the contour origin is unambiguous.
    # Convert the model start point from row/column indices to geographic coordinates.
    start_longitudes = np.interp(estimator.start_points[:, 1], np.arange(arrival_years.shape[1]), x_coordinates[0])
    start_latitudes = np.interp(estimator.start_points[:, 0], np.arange(arrival_years.shape[0]), y_coordinates[:, 0])
    axes.scatter(
        start_longitudes,
        start_latitudes,
        color=mpl.colormaps['YlOrBr_r'](0),
        edgecolor="white",
        linewidth=0.8,
        s=45,
        label=f"Start point ({format_arrival_year(0, start_year)})",
        zorder=3,
    )
    # Overlay a tenth of the observations; fitting still uses the complete dataset.
    observation_handle = add_observation_markers(axes, estimator, satellite, marker_path, marker_size)
    # Add labels and metadata so the saved image is self-explanatory.
    axes.set_xlabel("Longitude") if satellite else axes.set_xlabel("Grid column")
    axes.set_ylabel("Latitude") if satellite else axes.set_ylabel("Grid row")
    background_text = " with Esri World Imagery" if satellite else ""
    axes.set_title(f"{crop.capitalize()} arrival times: {', '.join(layers) or 'no layers'}{background_text}")
    axes.set_aspect("equal")
    # Label the image markers and source explicitly, keeping the legend out of dense sites.
    handles, labels = axes.get_legend_handles_labels()
    axes.legend(handles + [observation_handle], labels + ["Original observations"], handler_map={OffsetImage: ObservationImageHandler()}, loc="upper right")
    figure.tight_layout()

    # Ensure the requested generated-plots directory exists before saving.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Save a high-resolution raster image and close the figure for script use.
    figure.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(figure)
    # Return fit information for callers that import this script as a module.
    return fit_result, arrival_years, output_path


def parse_arguments():
    """Parse command-line options for the plotting script."""
    # Define the command-line interface with sensible defaults for all supported crops.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crop", choices=("wheat", "maize", "rice"))
    parser.add_argument("layers", nargs="*", choices=("csi", "hydro", "prec", "sea", "tmean"))
    parser.add_argument("--dt", type=float, default=40.0, help="Years represented by one grid time step.")
    # Expose the date origin and contour horizon without requiring edits to the script.
    parser.add_argument("--start-year", type=float, help="Source year (negative for BC, positive for AD); uses stored metadata when available.")
    parser.add_argument("--contour-interval", type=float, default=1000.0, help="Minimum years between contours (default: 1000; at most twelve intervals).")
    parser.add_argument("--max-years", type=float, help="Elapsed-year horizon; defaults to the latest observation.")
    # Allow a different artwork or marker height without changing the plot code.
    parser.add_argument("--marker-image", type=Path, help="Observation marker image (default: plotting/created_plots/wheat.jpg).")
    parser.add_argument("--marker-size", type=float, default=12.0, help="Observation image height in points (default: 12).")
    parser.add_argument("--theta-start", type=float, nargs="+", help="Initial intercept and layer coefficients.")
    parser.add_argument("--lower-bound", type=float, default=-2.0)
    parser.add_argument("--upper-bound", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--satellite", action="store_true", help="Download and show Esri World Imagery under the contours.")
    parser.add_argument(
        "--satellite-alpha",
        type=float,
        default=0.65,
        help="Opacity of the satellite background, from 0 (transparent) to 1 (opaque).",
    )
    return parser.parse_args()


def main():
    """Run the fit and contour export from the command line."""
    # Read user-selected crop, layers, and optional fitting parameters.
    arguments = parse_arguments()
    parameter_count = len(arguments.layers) + 1
    theta_start = arguments.theta_start or [0.0] * parameter_count
    # Validate the parameter vector before invoking the model fit.
    if len(theta_start) != parameter_count:
        raise ValueError(f"Expected {parameter_count} theta values, received {len(theta_start)}.")
    # Validate the background opacity before passing it to matplotlib.
    if not 0.0 <= arguments.satellite_alpha <= 1.0:
        raise ValueError("--satellite-alpha must be between 0 and 1.")
    # Use a predictable generated-plots filename unless the caller overrides it.
    output_path = arguments.output or Path(__file__).parent / "created_plots" / f"{arguments.crop}_arrival_times.png"
    # Fit the model and write the requested labelled contour image.
    fit_result, _, saved_path = make_arrival_time_plot(
        arguments.crop,
        arguments.layers,
        np.asarray(theta_start, dtype=float),
        (arguments.lower_bound, arguments.upper_bound),
        arguments.dt,
        output_path,
        arguments.satellite,
        arguments.satellite_alpha,
        arguments.start_year,
        arguments.contour_interval,
        arguments.max_years,
        arguments.marker_image,
        arguments.marker_size,
    )
    # Report the output path and fitted parameters for reproducibility.
    print(f"Saved contour plot: {saved_path}")
    print(f"Fitted theta: {fit_result.x}")
    print(f"Final MSE: {fit_result.fun:.6f}")


if __name__ == "__main__":
    # Run the command-line entry point when this file is executed directly.
    main()
