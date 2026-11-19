# Notes

## 6 - 2026-11-13: Driveability analyzer
- `driveable.py` → `driveability_analyzer.py`; `DriveableMap` → `DriveabilityMap` (3D heading stack); config section `driveable` → `driveability`.  Vehicle limits (pitch, roll, step, roughness, margin) moved under `vehicle`; `max_slope_deg` split into `max_pitch_deg` and `max_roll_deg`.
- Decisions: 16 heading bins (8 computed, mirrored by the 180° symmetry); oriented rectangle footprint; any bad cell under it blocks; unknown cells and the map edge block; clearance = max rise above a footprint plane fit (so slopes pass, bumps fail).
- Plane fit generalized to any kernel (`fit_plane_over_kernel` in `terrain_analyzer.py`), shared by the terrain window and the footprint.
- Costmap stays heading-independent (any heading) for now.
- Plot: any/all/heading layers; heading slider (left/right keys) with a compass arrow; grid toggle (`g`); layer labels prefixed by stage; controls column widened so labels fit; bool layers use a fixed 0-1 color scale.
- Limits: slope uses the terrain window's grade, not the footprint's; `vehicle.height` is not checked (2.5D map has no overhangs).  The new pitch/roll/margin values are guesses to tune; step 0.1 m and clearance 0.1 m look large for an F1Tenth.
- Checked on both maps and synthetic rock/ramp data; no test files, per project default.

## 5 - 2026-11-13: Terrain analyzer and GridMap
- `terrain.py` renamed `terrain_analyzer.py`.  Added generic `GridMap` (grid + named layers + units); `HeightMap`/`TerrainMap` are now `GridMap`s, so pipeline export and plot layers are generic.  `DriveableMap`/`CostMap` unchanged until implemented.
- One weighted plane fit per cell gives gx, gy, grade, roughness, and curvature (single window, `terrain.window_size_m`, rounded to odd cells); steps are raw 8-neighbor differences, signed into up/down.
- `slope` (rad) replaced by `grade` (m/m).  `driveable.max_slope_deg` will need `tan()` when that stage is implemented.
- Known limits: the fit window blurs grade across sharp edges; `step_height` on a ramp reads about grade x cell size.
- Checked on synthetic ramp/bowl/step/hole data (exact to ~1e-9); no test files, per project default.

## 4 - 2026-11-13: Planning sim scaffold
- Added `planning_sim/`, same layout as `convoying_sim` (`main.py`, `config.yaml`, `plot.py`, `core/`).  Stages are pure functions chained by `core/pipeline.py`.
- Only the height map loader and plotter are real; terrain, driveable, costmap, planner, and speed profile are stubs with placeholder outputs.
- Decisions: gray maps linearly to height (dark = low, so obstacles in `obstacle1_map.png` are pits); footprint inflation lives in `driveable`, so the costmap only adds soft costs; `Path` carries theta for a future kinematic planner; `HeightMap` has a validity mask for RTAB-Map unknowns.
- Plotter (`LayerView`): radio buttons or up/down keys switch the layer; checkbox or `t` toggles the trajectory.
- Docs split into Convoying Sim / Planning Sim sections.

## 3 - 2026-11-13: Speed-up and legend placement
- Profiling showed ~97% of the time in the MPC solve, from scipy's finite-difference gradients (~21 cost calls per gradient).  Added an analytic gradient (`MPC.cost_and_gradient`, checked against finite differences to ~1e-7): full 60 s run 26 s -> ~7 s.
- Error statistics are statistically unchanged but not bit-identical, since the optimizer path shifts slightly.
- A numpy-vectorized rollout alone was slower (N=10 is too small), so it was not kept.
- Live view: `tight_layout` once instead of per frame, and the frame is rendered before pacing so it holds real time (~103 ms per 100 ms step).
- Legend moved outside the world view, to the right (`plot.legend_*`, `plot.live_right_margin` in `config.yaml`).  This also removed the slow `loc='best'` search.

## 2 - 2026-11-13: Config yaml, sim/main split, core package
- All tunables moved to `convoying_sim/config.yaml` (loaded by `core/config.py`); classes take config sections, no duplicated defaults.
- `core/sim.py` is now a `Simulation` class; `main.py` runs it, `core/live.py` holds the live view, `plot.py` plots saved results.
- Code moved under `core/`; only `main.py`, `plot.py`, and `config.yaml` are top level.
- Fixed bug: follower EKF `x0` was `-following_distance*id`; now `-following_distance` (the true initial offset).  Verified the refactor was bit-identical to the old results before applying the fix.
- Added `pyyaml` to `requirements.txt`.

## 1 - 2026-11-13: Merged simulators into convoying_sim
- Merged `notrack_control`, `_scaled`, and `_errorplot` into `convoying_sim/`; based on errorplot (best tuning, headless sim, metrics).
- `visualization_mode` config (`LIVE` / `END_PLOT`) selects the live view or the end plot; `plot.py` is now shared by both.
- Kept `dt*Q` covariance scaling from `_scaled`; needs to go to hardware (see `to_hardware.md`).
- Errorplot added `Q` three times per step (lidar, pozyx, final predict), so `q` is now 0.3 /s (was 0.01 per call) to match its error statistics; not bit-identical to the old saved runs.
- Restyled all files to `style.md`; old folders removed (old data lives in `convoy_data`).
