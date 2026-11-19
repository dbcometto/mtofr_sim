"""Defines the bicycle dynamics model shared by BicycleHardware and the MPC solver"""
import math


def bicycle_step(x: float, y: float, theta: float, vel: float, steer: float, wheelbase: float,
                  min_speed: float, max_speed: float, min_steer: float, max_steer: float,
                  dt: float) -> tuple:
    """Advances a bicycle-model pose by one timestep under (vel, steer), clamped to the
    platform's limits. Plain floats/math (not numpy), and no WorldState/Hardware object
    involved, so this same pure function can run identically inside BicycleHardware
    (real dynamics) and inside the MPC solver's rollout (predicted dynamics) -- including
    inside a separate worker process, where only plain floats need to cross the boundary.
    Returns (x, y, theta, vx, vy, vtheta)."""
    speed = min(max(vel, min_speed), max_speed)
    steer_clamped = min(max(steer, min_steer), max_steer)

    vtheta = (speed / wheelbase) * math.tan(steer_clamped)
    new_theta = theta + vtheta * dt
    vx = speed * math.cos(new_theta)
    vy = speed * math.sin(new_theta)

    return x + vx * dt, y + vy * dt, new_theta, vx, vy, vtheta
