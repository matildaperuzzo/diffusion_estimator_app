import numpy as np

def calculate_errors(dataset, T, dt = 1):
    if dt <= 0:
        raise ValueError("dt must be a positive number.")
    errors = np.zeros(len(dataset))
    for i in range(len(dataset)):
        x, y = int(dataset[i,0]), int(dataset[i,1])
        errors[i] = dataset[i,2] - T[x,y]
    return errors*dt

def calculate_rmse(dataset, T, dt = 1):
    errors = calculate_errors(dataset, T, dt)
    rmse = np.sqrt(np.mean(errors**2))
    return rmse

def calculate_mse(dataset, T, dt = 1):
    errors = calculate_errors(dataset, T, dt)
    mse = np.mean(errors**2)
    return mse

