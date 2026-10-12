# Template function for a controller. Add your controller that determines p_bat at the TODO.
# The function signature must be exactly like this, as this function is passed into the simulator, and called from there

# The function assumes the following:
# - P_consumption is always positive (as the house appliances will never return power)
# - P_solar is always positive (as the solar panels will only supply)
# - P_bat can be positive or negative. Positive means discharging, supplying power to the load or back to the grid. Negative means charging
# - The simulator uses the solar and consumption inputs together with p_bat to determine p_grid such that:
#           P_grid = P_consumption - P_bat - P_solar
def template(
        t: float,
        dt: float,
        soc: float,
        p_solar: float,
        p_consumption: float,
        battery_capacity: float,
) -> float:
    # TODO: logic that decides how much battery you would like to use
    p_bat = 0  # Theoretical ideal battery value your controller would want to apply if SoC and other limits are no problem

    # =========================================================================================================
    # Below are a bunch of limits you should be respecting. The simulator does not care about the SoC going out of [0,1]
    # range. So the controller is responsible for checking that. I do realize this could be a separate function that
    # performs the limiting, but for flexibility i leave it here
    #
    # These lines are required to be their, as otherwise simulator SoC logic will fail.
    # Always make sure your controller takes this into account at the end.

    # TODO: here, you may add further limiting checks. Such as a max P_discharge/P_charge values

    # Ensuring SoC does not go <0 or >1
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

