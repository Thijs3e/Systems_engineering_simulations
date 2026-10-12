import numpy as np

def downsample_average(data: np.ndarray, factor: int) -> np.ndarray:
    """
    Downsample an array by averaging groups of `factor` elements.

    Example:
        [1, 2, 3, 4, 4, 0, 0, 0]
        factor=4

        -> [2.5, 1.0]
    """
    if factor <= 0:
        raise ValueError("factor must be positive")

    if len(data) % factor != 0:
        raise ValueError(
            f"Array length {len(data)} is not divisible by factor {factor}"
        )

    return data.reshape(-1, factor).mean(axis=1)

def upsample_average(data: np.ndarray, factor: int) -> np.ndarray:
    """
    Inverse of downsampling-by-averaging.

    Example:
        [4, 2]
        factor=2

        -> [2, 2, 1, 1]
    """
    if factor <= 0:
        raise ValueError("factor must be positive")

    return np.repeat(data / factor, factor)