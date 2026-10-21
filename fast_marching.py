import numpy as np
# Import a min-heap so the next narrow-band point can be selected without scanning the full grid.
import heapq

def fast_marching(speed, start_points, W = None, latitudes=None):
    """
    Perform the Fast Marching Method to compute the arrival time of a front propagating through a
    medium with a given speed function.
    
    Parameters:
    speed : ndarray
        A 2D array representing the speed function of the medium.
    start_points : list of tuples
        A list of (x, y, time) tuples representing the initial points and their arrival times.
    W : ndarray, optional
        A 2D array representing the weight function of the medium. If None, it defaults to ones.

    Returns:
    T : ndarray
        A 2D array representing the arrival time of the front at each point.
    """

    T = np.ones_like(speed) * np.inf
    accepted = np.zeros_like(speed, dtype=bool)
    considered = np.zeros_like(speed, dtype=bool)
    # Keep one array containing only finalised arrival times for the upwind solver.
    accepted_times = np.full(T.shape, np.inf, dtype=float)
    # Store (arrival time, x index, y index) entries for the narrow band.
    heap = []

    neighbours = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    # Use latitude-aware east-west distances when geographic rows are supplied.
    if latitudes is None:
        latitudes = np.zeros(speed.shape[0])
    latitudes = np.asarray(latitudes, dtype=float).ravel()
    if latitudes.size != speed.shape[0]:
        raise ValueError("latitudes must contain one value for every speed-grid row.")

    if W is None:
        W = np.ones_like(speed)

    for start_point in start_points:
        # estimate points around starting points
        x = int(start_point[0])
        y = int(start_point[1])
        T[x, y] = 0.0
        accepted[x, y] = True
        accepted_times[x, y] = 0.0

        for i, (dx, dy) in enumerate(neighbours):
            new_x = x + dx
            new_y = y + dy
            if 0 <= new_x < speed.shape[0] and 0 <= new_y < speed.shape[1]:
                if not accepted[new_x, new_y]:
                    considered[new_x, new_y] = True
                    # Longitude steps shrink toward the poles by the cosine latitude factor.
                    step_scale = 1.0 if dx != 0 else np.cos(np.deg2rad(latitudes[new_x]))
                    s = step_scale * W[new_x, new_y] / speed[new_x, new_y]
                    # Use only accepted values in the upwind update.
                    T_candidate = calculate_T(accepted_times, new_x, new_y, s)
                    if T_candidate < T[new_x, new_y]:
                        T[new_x, new_y] = T_candidate
                        # Add the improved candidate to the priority queue.
                        heapq.heappush(heap, (T_candidate, new_x, new_y))

    # March through the narrow band in increasing arrival-time order.
    while heap:
        min_time, x, y = heapq.heappop(heap)

        # Ignore stale heap entries created before a later improvement.
        if accepted[x, y] or min_time != T[x, y]:
            continue

        # Freeze the smallest tentative arrival time.
        accepted[x, y] = True
        considered[x, y] = False
        # Add the newly accepted value to the reusable accepted-time array.
        accepted_times[x, y] = T[x, y]

        # Update each non-frozen neighbour using the same stencil as before.
        for i, (dx, dy) in enumerate(neighbours):
            new_x = x + dx
            new_y = y + dy
            if 0 <= new_x < speed.shape[0] and 0 <= new_y < speed.shape[1]:
                if not accepted[new_x, new_y]:
                    considered[new_x, new_y] = True
                    # Apply the same physical distance scaling for later updates.
                    step_scale = 1.0 if dx != 0 else np.cos(np.deg2rad(latitudes[new_x]))
                    s = step_scale * W[new_x, new_y] / speed[new_x, new_y]
                    # Use only accepted values in the upwind update.
                    T_candidate = calculate_T(accepted_times, new_x, new_y, s)
                    if T_candidate < T[new_x, new_y]:
                        T[new_x, new_y] = T_candidate
                        # Push every improvement; stale entries are discarded above.
                        heapq.heappush(heap, (T_candidate, new_x, new_y))

    return T

def calculate_T(T,i,j,s):
    nx = T.shape[0]
    ny = T.shape[1]

    if i == 0:
        a = T[i+1,j]
    elif i == nx-1:
        a = T[i-1,j]
    else:
        a = min(T[i-1,j], T[i+1,j])

    if j == 0:
        b = T[i,j+1]
    elif j == ny-1:
        b = T[i,j-1]
    else:
        b = min(T[i,j-1], T[i,j+1])

    if abs(a-b) >= s:
        T_candidate = min(a,b) + s
    else:
        T_candidate = 0.5 * (a + b + np.sqrt(np.maximum(0, 2*s**2 - (a-b)**2)));

    return T_candidate
