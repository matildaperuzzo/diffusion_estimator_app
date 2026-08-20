import numpy as np
import tqdm
from scipy.io import loadmat
import os


class DiffusionEstimator(object):
    def __init__(self, crop, layers, dataset = None, dt = 40):
        self.crop = crop
        self.layers = layers
        self.dt = dt
        
        if dataset is not None:
            self.dataset = dataset
        else:
            self.get_dataset()

        self.start_points = np.array([self.find_start_point()])

        self.objective_function = np.array([])
        

    def get_dataset(self, path = None):
        """
        Load the dataset from a .mat file.

        Parameters:
        - path: The path to the .mat file.

        Returns:
        - dataset: The loaded dataset as a NumPy array.
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if path is None:
            path = os.path.join(base_dir, "data", self.crop, "raw_data.mat")
        elif not os.path.isabs(path):
            candidate = os.path.join(base_dir, path)
            if os.path.exists(candidate):
                path = candidate
        self.dataset = loadmat(path)['raw_data']

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
        import build_speed as bs
        return bs.build_speed(self.crop, theta, self.layers)

    def get_arrival_times(self, speed):
        """
        Compute the arrival times using the fast marching method.

        Parameters:
        - speed: A 2D array representing the speed function.

        Returns:
        - T: A 2D array of arrival times.
        """
        import fast_marching as fm
        return fm.fast_marching(speed, [tuple(sp) for sp in self.start_points])

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

    def sweep_theta(self, theta_range, num_points):
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
            T = self.get_arrival_times(speed)
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

    def fit_theta(self, theta_start, theta_bounds=None):
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
            T = self.get_arrival_times(speed)
            return self.calculate_error(T)

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

if __name__ == "__main__":
    crop = 'maize'
    layers = ["sea"]
    estimator = DiffusionEstimator(crop, layers)
    theta_range = np.array([[-2,-2], [2,2]])
    num_points = 21
    min_theta, min_error = estimator.sweep_theta(theta_range, num_points)
    estimator.plot_objective_function()
    print(f"Minimum theta: {min_theta}")
    print(f"Minimum error: {min_error}")
    result = estimator.fit_theta(min_theta, theta_bounds=[(-2, 2), (-4, 4)])
    print(f"Fitted theta: {result}")