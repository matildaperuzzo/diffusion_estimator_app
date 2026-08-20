import numpy as np
from scipy.io import loadmat
import os

def build_speed(crop, theta, layers):
    """
    Build a speed function based on the given crop, theta, and layers.

    Parameters:
    crop : str
        The type of crop for which to build the speed function.
    theta : np.ndarray
        a 1D array of weights for different layers + average layer
    layers : list
        List of layer names

    Returns:
    speed : ndarray
        A 2D array representing the speed function.
    """

    # check that theta is a 1D array and has the same length as layers + 1
    if not isinstance(theta, np.ndarray) or theta.ndim != 1:
        raise ValueError("theta must be a 1D numpy array.")

    crops = ['wheat','maize','rice']
    all_layers = ['csi','hydro','prec','sea','tmean']

    if crop not in crops:
        raise ValueError(f"Invalid crop type. Expected one of {crops}, got {crop}.")
    for layer in layers:
        if layer not in all_layers:
            raise ValueError(f"Invalid layer name. Expected one of {layers}, got {layer}.")

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", crop)
    if len(layers) == 0:
        layer_size = loadmat(f"{path}/sea.mat")["sea"].shape
        speed = np.zeros(layer_size, dtype=np.float64) + theta[0]
    else:
        for l,layer in enumerate(layers):
            # Load the layer data from the corresponding .mat file
            layer_data = loadmat(f"{path}/{layer}.mat")[layer]

            # check if speed is already initialized
            if 'speed' not in locals():
                speed = np.zeros_like(layer_data, dtype=np.float64) + theta[0]
                speed += theta[l+1] * layer_data
            else:
                speed += theta[l+1] * layer_data

    speed = 1 / (1 + np.exp(-speed))  # Apply sigmoid function to normalize speed values
    
    return speed