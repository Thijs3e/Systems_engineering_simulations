from typing import Callable
import math

import numpy as np
import matplotlib.pyplot as plt


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
        start_time: float = 0.0,
        sim_time: float = 24.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    :param p_solar: Solar generation over the simulation time, each timestep must be in kW
    :param p_consumption: Household power consumption over the simulation time, each timestep must be in kW
    :param c_init: initial battery state of charge, must be between 0 and 1
    :param total_capacity: total battery capacity in kWh
    :param dt: Timestep in hours, must be a divisor of 'sim_time' parameter
    :param control: A function that determines the amount of power the battery wil provide for that timestep, based on the conditions
    :param start_time: time at which the simulation starts. Used if not starting at 0
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
    if not (0 <= c_init <= 1):
        raise ValueError(
            f"Initial SoC must be in [0,1], got {c_init}"
        )

    p_grid = np.zeros(n)
    p_bat = np.zeros(n)
    c_bat = np.zeros(n + 1)
    c_bat[0] = c_init

    e_bat = c_init * total_capacity

    for i in range(n):
        t = (i * dt + start_time) % 24
        soc = c_bat[i]
        p_bat[i] = control(
            t=t,
            dt=dt,
            soc=soc,
            p_solar=p_solar[i],
            p_consumption=p_consumption[i],
            battery_capacity=total_capacity
        )
        p_grid[i] = p_consumption[i] - p_bat[i] - p_solar[i]  # could technically be resolved outside the loop
        e_bat -= p_bat[i] * dt  # positive p_bat means discharging the battery, hence -=
        c_bat[i + 1] = e_bat / total_capacity

    return p_grid, c_bat, p_bat


def plot_results(
        p_consumption: np.ndarray,
        p_solar: np.ndarray,
        p_grid: np.ndarray,
        p_bat: np.ndarray,
        c_bat: np.ndarray,
        dt: float,
        start_time: float = 0.0,
):
    n = len(p_grid)
    t = np.arange(n) * dt + start_time
    # t = (np.arange(n) * dt + start_time) % 24

    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    fig.suptitle("Simulation results")

    # Consumption
    axs[0, 0].step(t, p_consumption, where="post")
    axs[0, 0].set_title("Household Consumption")
    axs[0, 0].set_ylabel("Power [kW]")
    axs[0, 0].grid(True)
    axs[0, 0].set_ylim(-0.05 * np.max(p_consumption),
                       1.1 * np.max(p_consumption))
    # Solar
    axs[0, 1].step(t, p_solar, where="post", color="orange")
    axs[0, 1].set_title("Solar Generation")
    axs[0, 1].set_ylabel("Power [kW]")
    axs[0, 1].grid(True)
    axs[0, 1].set_ylim(-0.05 * np.max(p_solar),
                       1.1 * np.max(p_solar))
    # Grid
    axs[1, 0].step(t, p_grid, where="post", color="red")
    axs[1, 0].axhline(0, color="black", linewidth=0.8)
    axs[1, 0].set_title("Grid Power")
    axs[1, 0].set_xlabel("Time [h]")
    axs[1, 0].set_ylabel("Power [kW]")
    axs[1, 0].grid(True)
    ymin = min(0, np.min(p_grid))
    ymax = max(0.1, np.max(p_grid))
    padding = 0.05 * (ymax - ymin)
    axs[1, 0].set_ylim(
        ymin - padding,
        ymax + padding
    )

    # Battery power + SOC
    ax_bat = axs[1, 1]
    ax_soc = ax_bat.twinx()

    ax_bat.step(
        t,
        p_bat,
        where="post",
        color="green",
        label="P_bat"
    )

    ax_soc.plot(
        np.arange(len(c_bat)) * dt,
        c_bat,
        color="blue",
        label="SoC"
    )

    ax_bat.axhline(0, color="black", linewidth=0.8)

    ax_bat.set_title("Battery")
    ax_bat.set_xlabel("Time [h]")
    ax_bat.set_ylabel("Power [kW]", color="green")
    ax_soc.set_ylabel("SoC [-]", color="blue")

    # Combined legend
    lines1, labels1 = ax_bat.get_legend_handles_labels()
    lines2, labels2 = ax_soc.get_legend_handles_labels()
    ax_bat.legend(lines1 + lines2, labels1 + labels2)

    ax_bat.grid(True)

    plt.tight_layout()
    plt.show()
