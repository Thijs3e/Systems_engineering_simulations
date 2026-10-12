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