from typing import Callable
import math

import numpy as np


def get_float_divisor(b, a, tolerance=1e-9):
    """Checks if float 'a' fits an integer amount into float 'b'.

    Returns the integer multiplier if true, or None if it doesn't fit evenly.
    """
    if a == 0:
        raise ValueError("Divisor cannot be zero.")

    ratio = b / a
    nearest_int = round(ratio)

    # Check if the ratio is close enough to an integer
    if math.isclose(ratio, nearest_int, rel_tol=tolerance, abs_tol=tolerance):
        return int(nearest_int)

    return None


def simulate(
        p_solar: np.ndarray,
        p_consumption: np.ndarray,
        c_init: float,
        total_capacity: float,
        dt: float,  # Timestep in hours
        control: Callable,
        sim_time=24.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    :param p_solar: Solar generation over the simulation time, each timestep must be in kW
    :param p_consumption: Household power consumption over the simulation time, each timestep must be in kW
    :param c_init: initial battery state of charge, must be between 0 and 1
    :param total_capacity: total battery capacity in kWh
    :param dt: Timestep in hours, must be a divisor of 'sim_time' parameter
    :param control: A function that determines the amount of power the battery wil provide for that timestep, based on the conditions
    :param sim_time: total simulation time, 24 hours by default
    :return: Returns a tuple with p_grid, c_bat and p_bat
    """
    n: int | None = get_float_divisor(sim_time, dt)
    if n is None:
        raise ValueError(f"Simulation step {dt} is not a divisor of simulation time {sim_time}")
    if len(p_consumption) != n:
        raise ValueError(
            f"Power consumption array length {len(p_consumption)} is not the same as number of simulation timesteps {n}"
        )
    if len(p_solar) != n:
        raise ValueError(
            f"Solar power array length {len(p_solar)} is not the same as number of simulation timesteps {n}"
        )

    p_grid = np.zeros(n)
    p_bat = np.zeros(n)
    c_bat = np.zeros(n+1)
    c_bat[0] = c_init

    e_bat = c_init*total_capacity

    for i in range(n):
        t = i*dt
        soc = c_bat[i]
        p_bat[i] = control(
            t=t,
            dt=dt,
            soc=soc,
            p_solar=p_solar[i],
            p_consumption=p_consumption[i],
            cap=total_capacity
        )
        p_grid[i] = p_consumption[i]-p_bat[i]-p_solar[i] # could technically be resolved outside the loop
        e_bat -= p_bat[i]*dt # positive p_bat means discharging the battery, hence -=
        c_bat[i+1] = e_bat/total_capacity

    return p_grid, c_bat, p_bat