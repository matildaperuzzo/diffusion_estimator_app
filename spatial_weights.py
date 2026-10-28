"""Build the latitude weights shared by both propagation solvers."""

# Keep the geographic weight on the same grid as the supplied speed field.
import numpy as np


def resolve_spatial_weights(
    shape: tuple[int, int],
    *,
    apply_w: bool = True,
    latitudes: np.ndarray | None = None,
    W: np.ndarray | None = None,
) -> np.ndarray:
    """Return MATLAB's positive cosine-latitude weights, or unit weights."""
    # Opting out means neither a supplied raster nor latitude changes propagation.
    if not apply_w:
        return np.ones(shape, dtype=float)

    # An explicit raster preserves the low-level fast-marching API.
    if W is not None:
        weights = np.asarray(W, dtype=float)
        if weights.shape != shape:
            raise ValueError("W must have the same shape as speed.")
    else:
        # A cropped grid's geographic latitude cannot be inferred from its shape.
        if latitudes is None:
            raise ValueError("latitudes or W is required when apply_w is True.")
        row_latitudes = np.asarray(latitudes, dtype=float).ravel()
        if row_latitudes.size != shape[0]:
            raise ValueError("latitudes must contain one value for every speed-grid row.")
        weights = np.broadcast_to(np.cos(np.deg2rad(row_latitudes))[:, None], shape)

    # Zero or non-finite weights would make Monte Carlo probabilities undefined.
    if not np.all(np.isfinite(weights)) or np.any(weights <= 0.0):
        raise ValueError("W must contain only positive finite values.")
    return weights
