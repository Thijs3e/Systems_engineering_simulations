import framework
import numpy as np

def zero_on_the_meter_control(t: float, dt: float, soc: float, p_solar: float, p_consumption: float, cap: float) -> float:
    # To supply with the grid at exactly 0, the battery should provide exactly p_consump - p_solar
    p_bat = p_consumption-p_solar


    # Always perform checks and revise the calculated values. For example based on max charge/discharge rate
    e_step = dt*p_bat
    e_max = cap*soc
    if e_step>e_max:
        # SoC would go negative if the energy consumed in this step is larger than the energy left in the battery
        frac = e_max/e_step
        return frac*p_bat # Scale down p_bat by the fraction that is still left in the battery
    return p_bat

if __name__ == '__main__':
    p_consumption = np.full(24, 0.5)
    # Morning peak: 06:00-09:00
    p_consumption[6:9] = 1.0
    # Lunch peak: 12:00-13:00
    p_consumption[12:13] = 1.0
    # Evening peak: 16:00-21:00
    p_consumption[16:21] = 1.0

    p_solar = np.zeros(24)
    # Solar generation from 07:00-19:00
    p_solar[7:19] = 1.0

    p_solar = np.tile(p_solar, 2)
    p_consumption = np.tile(p_consumption, 2)

    (p_grid, c_bat, p_bat) = framework.simulate(
        p_solar=p_solar,
        p_consumption=p_consumption,
        c_init=0.5,
        total_capacity=10,
        dt=1,
        control=zero_on_the_meter_control,
        sim_time=48
    )

    framework.plot_results(
        p_consumption,
        p_solar,
        p_grid,
        p_bat,
        c_bat,
        1
    )