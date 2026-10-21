import numpy as np
# Keep tqdm optional so fitting and plotting work in minimal environments.
try:
    import tqdm
except ImportError:
    tqdm = None
from pathlib import Path
from scipy.io import loadmat
import os

# Import the standardized HDF5 loaders used by the estimator.
from processing.load_data import load_data
from processing.load_layers import TRACE_LAYERS, load_layer


# Map the estimator's historical layer names to standardized HDF5 filenames.
LAYER_FILE_NAMES = {
    "csi": "csidata",
    "hydro": "acc",
    "prec": "prec",
    "sea": "sea",
    "tmean": "temp",
}


class DiffusionEstimator(object):
    def __init__(self, crop, layers, dataset=None, dt=40, buffer_size_rad=0.0, data_directory=None, delta=0.5):
        """Load point observations and environmental layers on a common degree-based grid.

        ``delta`` controls the spatial resolution in degrees. Stored crop extents
        already include padding; ``buffer_size_rad`` adds an optional extra buffer.
        An explicit ``dataset`` uses zero-based spatial indices on this grid and
        one-based time indices in units of ``dt``, as in the existing estimator API.
        """
        # Reject invalid resolutions, time steps, and extra padding before reading data.
        if not np.isfinite(delta) or delta <= 0:
            raise ValueError("delta must be finite and positive.")
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be finite and positive.")
        if not np.isfinite(buffer_size_rad) or buffer_size_rad < 0:
            raise ValueError("buffer_size_rad must be finite and non-negative.")
        # Store the model configuration before loading its spatial inputs.
        self.crop = crop.lower()
        self.layers = list(layers)
        self.dt = dt
        self.delta = delta

        # Resolve the processed-data directory relative to this module by default.
        processed_directory = Path(data_directory) if data_directory is not None else Path(__file__).resolve().parent / "data" / "processed"
        # Keep the crop and environmental layer subdirectories separate.
        self.data_directory = processed_directory
        crop_directory = processed_directory / "crop"
        layer_directory = processed_directory / "layers"

        # Read the point object; its coordinate lists are observations, not raster axes.
        self.crop_points = load_data(self.crop, crop_directory)
        self.start_time = self.crop_points["start_time"]
        # Retain the stored degree extents and convert only the optional extra buffer.
        buffer_degrees = np.degrees(buffer_size_rad)
        extra_padding = np.array([-buffer_degrees, buffer_degrees])
        latitude_extent = tuple(np.clip(self.crop_points["lat_extent"] + extra_padding, -90.0, 90.0))
        longitude_extent = tuple(np.clip(self.crop_points["lon_extent"] + extra_padding, -180.0, 180.0))
        self.latitude_extent = latitude_extent
        self.longitude_extent = longitude_extent
        # Match the inspection notebook's inclusive observed-year window for climate layers.
        self.year_extent = (
            float(self.crop_points["time"].min()),
            float(self.crop_points["time"].max()),
        )

        # Load every requested environmental layer on the crop's common grid.
        self.layer_data = {}
        self.latitude = None
        self.longitude = None
        # A model with only an intercept still needs the target grid; use the sea mask's axes.
        for layer_name in self.layers or ["sea"]:
            standardized_name = LAYER_FILE_NAMES.get(layer_name, layer_name)
            loaded_layer = load_layer(
                standardized_name,
                latitude_extent,
                longitude_extent,
                year_extent=self.year_extent if standardized_name in TRACE_LAYERS else None,
                layer_directory=layer_directory,
                delta=self.delta,
            )
            # Establish the grid from the first layer and require subsequent layers to align.
            if self.latitude is None:
                self.latitude = loaded_layer["lat"]
                self.longitude = loaded_layer["lon"]
            elif not (
                np.array_equal(self.latitude, loaded_layer["lat"])
                and np.array_equal(self.longitude, loaded_layer["lon"])
            ):
                raise ValueError(f"Layer {layer_name} does not share the requested delta={self.delta} grid.")
            # Keep the fallback sea mask out of an intercept-only model's explanatory layers.
            if self.layers:
                self.layer_data[layer_name] = loaded_layer["data"]
        self.grid_shape = (self.latitude.size, self.longitude.size)
        
        if dataset is not None:
            # Preserve the existing explicit-data API without mutating the caller's array.
            self.dataset = np.array(dataset, dtype=float, copy=True)
        else:
            self.get_dataset()

        # Expose the observed crop points separately from the spatial crop grid.
        self.crop_data = self.dataset

        self.start_points = np.array([self.find_start_point()])

        self.objective_function = np.array([])
        

    def get_dataset(self, path = None):
        """
        Map crop HDF5 points onto the loaded grid, or import an explicit legacy .mat file.

        Parameters:
        - path: Optional legacy .mat file; omitted uses the loaded crop point object.

        Returns:
        - dataset: The loaded dataset as a NumPy array.
        """
        if path is None:
            # Recompute spatial indices from geographic locations whenever delta changes.
            rows = np.abs(self.latitude[:, None] - self.crop_points["lat"]).argmin(axis=0)
            columns = np.abs(self.longitude[:, None] - self.crop_points["lon"]).argmin(axis=0)
            # Preserve the saved temporal bins and express elapsed time in the model's dt units.
            # find_start_point subtracts the one-based time offset once during construction.
            time_indices = 1.0 + (
                (self.crop_points["index"][:, 2] - 1) * self.crop_points["time_step"] / self.dt
            )
            self.dataset = np.column_stack((rows, columns, time_indices))
            return
        # Retain explicit legacy-file imports for callers that still supply MATLAB observations.
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if not os.path.isabs(path):
            candidate = os.path.join(base_dir, path)
            if os.path.exists(candidate):
                path = candidate
        # Use signed indices so subtracting the MATLAB one-based offset cannot wrap.
        self.dataset = np.asarray(loadmat(path)['raw_data'], dtype=float).copy()
        # Map the original regional grid indices onto the loaded coordinate vectors.
        extent_file = Path(base_dir) / "data" / f"{self.crop}_latlon.mat"
        original_grid_file = Path(base_dir) / "data" / self.crop / "sea.mat"
        if extent_file.exists() and original_grid_file.exists():
            extent = loadmat(extent_file)
            original_shape = loadmat(original_grid_file)["sea"].shape
            original_latitude = np.linspace(*np.asarray(extent["lats"]).ravel(), original_shape[0])
            original_longitude = np.linspace(*np.asarray(extent["lons"]).ravel(), original_shape[1])
            # Convert MATLAB rows and columns to geographic locations before finding new indices.
            rows = self.dataset[:, 0].astype(int) - 1
            columns = self.dataset[:, 1].astype(int) - 1
            self.dataset[:, 0] = np.abs(self.latitude[:, None] - original_latitude[rows]).argmin(axis=0)
            self.dataset[:, 1] = np.abs(self.longitude[:, None] - original_longitude[columns]).argmin(axis=0)

    def find_start_point(self):
        """
        Find the starting point in the dataset where the third column is zero.

        Returns:
        - start_point: The starting point as a NumPy array.
        """
        # Adjust the third column of the dataset
        self.dataset[:, 2] = self.dataset[:, 2] - 1
        
        # Find the index of the first occurrence where the third column is zero
        start_index = np.where(self.dataset[:, 2] == 0)[0][0]
        
        # Extract the starting point from the dataset
        start_point = self.dataset[start_index, :]
        
        return start_point

    def add_start_point(self, start_point):
        """
        Add a new starting point to the list of starting points.

        Parameters:
        - start_point: A NumPy array representing the new starting point.
        """
        self.start_points = np.vstack([self.start_points, start_point])


    def build_speed(self, theta):
        """
        Build a speed function based on the given crop, theta, and layers.

        Parameters:
        - theta: A 1D array of weights for different layers + average layer.

        Returns:
        - speed: A 2D array representing the speed function.
        """
        # Validate the coefficient vector against the intercept plus layer terms.
        theta = np.asarray(theta, dtype=float)
        if theta.ndim != 1 or theta.size != len(self.layers) + 1:
            raise ValueError("theta must contain one intercept and one coefficient per layer.")

        # Start from the intercept and add each loaded standardized layer.
        linear_speed = np.full(self.grid_shape, theta[0], dtype=float)
        for index, layer_name in enumerate(self.layers, start=1):
            linear_speed += theta[index] * self.layer_data[layer_name]

        # Apply the same sigmoid normalization used by the original estimator.
        return 1.0 / (1.0 + np.exp(-linear_speed))

    def get_arrival_times(self, speed, latitudes=None, method="fast_marching", n_reps=100, random_state=None):
        """
        Compute arrival times using fast marching or Monte Carlo propagation.

        Parameters:
        - speed: A 2D array representing the speed function.

        Returns:
        - T: A 2D array of arrival times.
        """
        # Dispatch explicitly so both solving methods share the estimator API.
        if method == "monte_carlo":
            from monte_carlo import simulate_arrival_times
            return simulate_arrival_times(speed, [tuple(sp) for sp in self.start_points], n_reps, random_state)
        if method != "fast_marching":
            raise ValueError("method must be 'fast_marching' or 'monte_carlo'.")

        # Use the loaded latitude grid unless a caller supplies another one.
        import fast_marching as fm
        selected_latitudes = self.latitude if latitudes is None else latitudes
        return fm.fast_marching(speed, [tuple(sp) for sp in self.start_points], latitudes=selected_latitudes)

    def calculate_simulation_times_and_error(self, speed, n_reps=100, dt=None, random_state=None):
        """Calculate Monte Carlo simulation times and mean squared error."""
        # Keep the Monte Carlo calculation available as a single estimator operation.
        from monte_carlo import calculate_simulation_times_and_error
        selected_dt = self.dt if dt is None else dt
        return calculate_simulation_times_and_error(
            speed,
            self.dataset,
            [tuple(sp) for sp in self.start_points],
            n_reps,
            selected_dt,
            random_state,
        )

    def calculate_error(self, T):
        """
        Calculate the mean squared error between the computed arrival times and the dataset.

        Parameters:
        - T: A 2D array of computed arrival times.

        Returns:
        - error: The mean squared error.
        """
        import calculate_errors as ce
        return ce.calculate_mse(self.dataset, T, self.dt)

    def sweep_theta(self, theta_range, num_points, method="fast_marching", n_reps=100, random_state=None):
        """
        Perform a sweep over the specified range of theta values.

        Parameters:
        - theta_range: A 2xN array with N being the number of layers + 1
        - num_points: Number of points to sample in the range.

        Returns:
        - results: A list of mean squared errors corresponding to each theta value.
        """
        all_thetas = [np.linspace(theta_range[0, i], theta_range[1, i], num_points) for i in range(theta_range.shape[1])]
        all_theta_combinations = np.array(np.meshgrid(*all_thetas)).T.reshape(-1, theta_range.shape[1])
        objective_function = np.zeros([all_theta_combinations.shape[0], len(theta_range[1]) + 1])
        for i, theta in enumerate(tqdm.tqdm(all_theta_combinations, desc='Evaluating theta combinations')):
            speed = self.build_speed(theta)
            # Use the selected solver for every parameter combination.
            T = self.get_arrival_times(speed, method=method, n_reps=n_reps, random_state=random_state)
            error = self.calculate_error(T)
            objective_function[i, :theta.shape[0]] = theta
            objective_function[i, -1] = error

        self.objective_function = np.vstack([self.objective_function, objective_function]) if self.objective_function.size else objective_function
        min_error_index = np.argmin(self.objective_function[:, -1])
        min_theta = self.objective_function[min_error_index, :-1]
        min_error = self.objective_function[min_error_index, -1]
        return min_theta, min_error


    def plot_objective_function(self):
        """
        Plot the objective function (mean squared error) against the theta values.
        """
        import matplotlib.pyplot as plt
        from scipy.interpolate import griddata
        
        if np.shape(self.objective_function)[1] == 3:
            theta_1 = self.objective_function[:, 0]
            theta_2 = self.objective_function[:, 1]
            errors = self.objective_function[:, 2]
            meshgrid = np.meshgrid(theta_1, theta_2)
            Z = griddata((theta_1, theta_2), errors, (meshgrid[0], meshgrid[1]), method="linear")
            plt.figure(figsize=(10, 6))
            plt.contourf(meshgrid[0], meshgrid[1], Z, levels=50, cmap='viridis')
            plt.colorbar(label='Mean Squared Error')
            plt.xlabel('Theta 1')
            plt.ylabel('Theta 2')
            plt.title('Objective Function: Mean Squared Error vs Theta Values')
            plt.show()
        else:
            print("Plotting not supported for this number of theta dimensions.")

    def fit_theta(self, theta_start, theta_bounds=None, method="fast_marching", n_reps=100, random_state=None):
        """
        Fit the theta parameters using projected gradient descent.

        Parameters:
        - theta_start: Initial guess for the theta parameters.
        - theta_bounds: Bounds for the theta parameters.

        Returns:
        - result: A dict containing the final theta, error, and iteration history.
        """
        def objective(theta):
            speed = self.build_speed(theta)
            # Evaluate the objective with the selected numerical solver.
            return self.calculate_error(self.get_arrival_times(
                speed,
                method=method,
                n_reps=n_reps,
                random_state=random_state,
            ))

        theta = np.array(theta_start, dtype=float).copy()
        if theta_bounds is None:
            theta_bounds = (-np.inf, np.inf)
        theta_bounds = np.array(theta_bounds, dtype=float)

        if theta_bounds.ndim == 1:
            lower_bounds = np.full(theta.shape, theta_bounds[0], dtype=float)
            upper_bounds = np.full(theta.shape, theta_bounds[1], dtype=float)
        else:
            lower_bounds = theta_bounds[:, 0]
            upper_bounds = theta_bounds[:, 1]

        def project(values):
            return np.minimum(np.maximum(values, lower_bounds), upper_bounds)

        def finite_difference_gradient(values, epsilon=1e-4):
            gradient = np.zeros_like(values, dtype=float)
            for index in range(values.size):
                step = np.zeros_like(values, dtype=float)
                step[index] = epsilon
                forward = objective(project(values + step))
                backward = objective(project(values - step))
                gradient[index] = (forward - backward) / (2 * epsilon)
            return gradient

        max_iter = 10
        initial_learning_rate = 0.05
        min_learning_rate = 1e-8
        backtrack_factor = 0.5
        armijo_c = 1e-8
        tolerance = 1e5
        history = []

        for iteration in range(1, max_iter + 1):
            error = objective(theta)
            gradient = finite_difference_gradient(theta)
            grad_norm = np.linalg.norm(gradient)

            if grad_norm < tolerance:
                history.append({
                    "iteration": iteration,
                    "theta": theta.copy(),
                    "error": float(error),
                    "gradient": gradient.copy(),
                    "gradient_norm": float(grad_norm),
                    "learning_rate": 0.0,
                    "accepted": True,
                })
                print(
                    f"Iteration {iteration:03d} | error={error:.6f} | "
                    f"grad_norm={grad_norm:.6f} | lr=0.0 | accepted=True | theta={theta}"
                )
                break

            learning_rate = initial_learning_rate
            accepted = False
            candidate_theta = theta.copy()
            candidate_error = error

            # Backtracking line search with projection to avoid bouncing on bounds.
            while learning_rate >= min_learning_rate:
                trial_theta = project(theta - learning_rate * gradient)

                # If projection keeps us at the same point, shrink step and retry.
                if np.allclose(trial_theta, theta, rtol=0.0, atol=1e-12):
                    learning_rate *= backtrack_factor
                    continue

                trial_error = objective(trial_theta)
                sufficient_decrease = error - armijo_c * learning_rate * (grad_norm ** 2)

                if trial_error <= sufficient_decrease:
                    candidate_theta = trial_theta
                    candidate_error = trial_error
                    accepted = True
                    break

                learning_rate *= backtrack_factor

            history.append({
                "iteration": iteration,
                "theta": theta.copy(),
                "error": float(error),
                "gradient": gradient.copy(),
                "gradient_norm": float(grad_norm),
                "learning_rate": float(learning_rate),
                "accepted": bool(accepted),
                "next_error": float(candidate_error),
            })

            print(
                f"Iteration {iteration:03d} | error={error:.6f} | "
                f"grad_norm={grad_norm:.6f} | lr={learning_rate:.3e} | "
                f"accepted={accepted} | theta={theta}"
            )

            if not accepted:
                print("Stopping: line search could not find a decreasing step.")
                break

            theta = candidate_theta

        final_error = objective(theta)
        print(f"Final theta: {theta}")
        print(f"Final error: {final_error:.6f}")

        from types import SimpleNamespace

        fit_result = SimpleNamespace(
            x=theta,
            fun=float(final_error),
            nit=len(history),
            history=history,
            success=True,
            message="Projected gradient descent completed.",
        )

        self.fit_history = history
        self.fit_result = fit_result
        return fit_result

# if __name__ == "__main__":
    # crop = 'wheat'
    # layers = ["prec","sea"]
    # estimator = DiffusionEstimator(crop, layers)
    # theta_range = np.array([(-2, 2), (-5, 5), (-5, 5)]).T
    # num_points = 11
    # min_theta, min_error = estimator.sweep_theta(theta_range, num_points)
    # estimator.plot_objective_function()
    # print(f"Minimum theta: {min_theta}")
    # print(f"Minimum error: {min_error}")
    # result = estimator.fit_theta(min_theta)
    # print(f"Fitted theta: {result}")

if __name__ == "__main__":
    crop = "wheat"
    layers = ["prec", "sea"]

    estimator = DiffusionEstimator(crop, layers)

    theta_range = np.array([
        (-2, 2),
        (-5, 5),
        (-5, 5),
    ]).T

    # Use fewer repetitions while testing; increase for better estimates.
    monte_carlo_reps = 6

    min_theta, min_error = estimator.sweep_theta(
        theta_range,
        num_points=3,
        method="monte_carlo",
        n_reps=monte_carlo_reps,
        random_state=42,
    )

    print(f"Minimum theta: {min_theta}")
    print(f"Minimum error: {min_error}")

    result = estimator.fit_theta(
        min_theta,
        method="monte_carlo",
        n_reps=monte_carlo_reps,
        random_state=42,
    )

    print(f"Fitted theta: {result}")
