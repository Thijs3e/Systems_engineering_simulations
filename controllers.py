def zero_on_the_meter_control(
        t: float,
        dt: float,
        soc: float,
        p_solar: float,
        p_consumption: float,
        battery_capacity: float,
) -> float:
    # Battery power required to make P_grid = 0
    p_bat = p_consumption - p_solar

    # Battery overcharge limits
    e_step = dt * p_bat

    e_available = battery_capacity * soc
    e_room = battery_capacity * (1 - soc)

    if e_step > e_available:
        frac = e_available / e_step
        return frac * p_bat

    if e_step < -e_room:
        frac = e_room / (-e_step)
        return frac * p_bat

    return p_bat


def battery_fixed_time_only(
        t: float,
        dt: float,
        soc: float,
        p_solar: float,
        p_consumption: float,
        battery_capacity: float
) -> float:
    start_time = 16.0
    end_time = 21.0

    # Discharge during evening peak
    if start_time <= t < end_time:
        p_bat = p_consumption - p_solar

    # Otherwise only charge from excess solar
    else:
        excess_solar = p_solar - p_consumption

        if excess_solar > 0:
            p_bat = -excess_solar
        else:
            p_bat = 0

    # Battery limits
    e_step = dt * p_bat

    e_available = battery_capacity * soc
    e_room = battery_capacity * (1 - soc)

    if e_step > e_available:
        frac = e_available / e_step
        return frac * p_bat

    if e_step < -e_room:
        frac = e_room / (-e_step)
        return frac * p_bat

    return p_bat
