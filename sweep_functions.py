import numpy as np
import itertools
import scipy.optimize as opt
import build_speed as bs
import fast_marching as fm
import calculate_errors as ce

def sweep(ranges, num_points, layers, dataset):
    """
    Perform a sweep over the specified ranges of parameters.

    Parameters:
    - ranges: List of tuples specifying the min and max values for each parameter.
    - num_points: Number of points to sample in each range.
    - layers: Additional layers or configurations needed for the sweep.
    - dataset: The dataset to evaluate the results against.
    
    Returns:
    - results: A list of results from the sweep.
    """
    # Generate a grid of parameter values based on the specified ranges and number of points
    param_grid = [np.linspace(r[0], r[1], num_points) for r in ranges]
    
    # Initialize a list to store results
    results = []

    # sweep over all combination of parameters
    for params in itertools.product(*param_grid):
        # Perform optimization or evaluation with the current set of parameters
        S = bs.build_speed(crop, theta, layers)
        start_point = find_start_point(dataset)
        T = fm.fast_marching(S, [tuple(start_point)])
        result = ce.calculate_mse(T, dataset)
        results.append(result)

    return results
    
def find_start_point(dataset):
    """
    Find the starting point in the dataset where the third column is zero.

    Parameters:
    - dataset: The input dataset as a NumPy array.

    Returns:
    - start_point: The starting point as a NumPy array.
    """
    # Adjust the third column of the dataset
    dataset[:, 2] = dataset[:, 2] - 1
    
    # Find the index of the first occurrence where the third column is zero
    start_index = np.where(dataset[:, 2] == 0)[0][0]
    
    # Extract the starting point from the dataset
    start_point = dataset[start_index, :]
    
    return start_point