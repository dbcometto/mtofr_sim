# Specification

Two simulators: `convoying_sim/` (the followers' algorithms) and `planning_sim/` (the leader's map-to-trajectory pipeline).





## Convoying Sim

`convoying_sim/` simulates an off-track convoy: a leader plus followers, each follower estimating and tracking the vehicle ahead.

### Layout
- `main.py`: entry point (`python convoying_sim/main.py`).  Builds the simulation, runs it, then saves and plots.
- `config.yaml`: every tunable parameter.  `_deg` keys are converted to radians (`_rad`) on load.
- `plot.py`: plots a saved results file.
- `core/sim.py`: `Simulation` class, the sim logic with no entry point.  `step()` advances one step; `build_results()` packages the history.
- `core/ekf.py`: per-follower EKF of the target's pose and speed in the follower's body frame, fed by lidar (x, y) and pozyx (range).
- `core/mpc.py`: per-follower MPC that tracks a target point behind the vehicle ahead; holds if the target is behind it.  Solved with L-BFGS-B using an analytic gradient and a shifted warm start.
- `core/vehicle.py`: bicycle model and `LEADER_ID`.
- `core/config.py`: yaml loader.
- `core/plotting.py`: world view and error plots.
- `core/live.py`: `LiveView`, the live window and manual leader keys.

### Per Step
1. Each EKF updates with noisy lidar and pozyx (and optionally the neighbors' commands, `sim.do_enable_crosstalk`).
2. The leader is commanded (circle, random, or manual).  Each follower's MPC solves from its EKF.
3. True dynamics advance on a simulated clock (`sim.dt`), independent of wall time.
4. Estimator error, tracking error, and lateral deviation from the leader's trail are recorded.

### Visualization (`run.visualization_mode`)
- `LIVE`: redraws each step, paced to real time; manual leader keys work only here.
- `END_PLOT`: runs as fast as possible, then shows the world view and error plots.
- Both save results to `run.output_file` if `run.do_save_results`.

### EKF Process Noise
`Q` is a per-second rate, scaled by the elapsed time in the covariance predict (`dt*Q`), so uncertainty growth does not depend on the update rate.






## Planning Sim

`planning_sim/` simulates the leader's planning pipeline: a 2.5D height map (on hardware, RTAB-Map point cloud → height map) is turned into a trajectory for the leader to follow.  Partly built: the height map loader, terrain analyzer, and plotter are real; the other stages are documented stubs with placeholder outputs (`TODO`s in the code).

### Layout
- `main.py`: entry point (`python planning_sim/main.py`).  Runs the pipeline, then saves and plots.
- `config.yaml`: every tunable parameter (map choice, start/goal, thresholds, vehicle dimensions, plot).
- `plot.py`: plots a saved results file.
- `maps/<name>/<name>.png` + `<name>.yaml`: a starting height map and its metadata, in a folder named after the map (`map.folder` in the config) (`cell_size_m`, `height_min_m`, `height_max_m`, `origin_px`).  Gray 0..255 maps linearly to the height range, dark = low.  `origin_px` is the `[x, y]` pixel (from the top left) that is world (0, 0); world +x is right, +y is up.
- `core/pipeline.py`: `run_pipeline()` chains the stages; `build_results()` packages the layers and trajectory for saving and plotting.
- `core/types.py`: `Grid`, `GridMap` (generic: a `Grid`, named layers, a unit per layer; `HeightMap` and `TerrainMap` are `GridMap`s with fixed layer names), `DriveabilityMap`, `CostMap`, `Path`, `Trajectory`, `PlanningResult`.
- `core/config.py`: yaml loader (same as the convoy sim's).
- `core/plotting.py`: `LayerView`, the map window.

### Stages
1. `core/heightmap.py`: map folder (image + yaml) → `HeightMap` (with a validity mask for unknown cells).
2. `core/terrain_analyzer.py`: `HeightMap` → `TerrainMap`; vehicle-independent, NaN where unknown or unreliable.
   - Plane fit `z = a + gx·x + gy·y` over the valid cells of a `terrain.window_size_m` window: `gx`, `gy` (m/m, uphill along world +x, +y), `grade` (`hypot`, m/m), `roughness` (RMS residual, m), `curvature` (1/m, + = dip, - = crest, from the center residual), `support` (valid fraction of the window).  Fit layers are NaN below `terrain.min_support`.
   - 8-neighbor steps: `step_up` (largest rise), `step_down` (largest drop), `step_height` (the larger), m.
3. `core/driveability_analyzer.py`: `HeightMap` + `TerrainMap` → `DriveabilityMap`; vehicle-specific (`vehicle.*` in the config).  `driveable[heading_bin, row, col]` says whether the vehicle center may sit in a cell at a heading (`driveability.heading_bins` evenly spaced over 360°; the second half circle mirrors the first).
   - Bad cell: unknown, `step_height > max_step_height`, `roughness > max_roughness`, or grade over the pitch (along the heading) or roll (across it) limit; NaN counts as bad.
   - A pose is blocked if any bad cell lies under the oriented footprint rectangle (+ `footprint_margin`; outside the map counts as bad).
   - Clearance: a plane is fit over the footprint cells, and the pose is blocked if any cell rises more than `clearance` above it (bumps, not slopes).
4. `core/costmap.py`: `DriveabilityMap` (+ `TerrainMap`) → `CostMap`; soft costs, infinite where not driveable (heading-independent for now: driveable at any heading).
5. `core/planner.py`: `CostMap` + start + goal → `Path` (x, y, theta).
6. `core/speed_profile.py`: `Path` → `Trajectory` (t, x, y, theta, vel, curvature).

### Visualization
`LayerView` shows one layer at a time, labeled by its stage (Height, Terrain, Driveability, Cost) (height, valid, gx, gy, grade, step height/up/down, roughness, curvature, support, driveable at any/all headings, driveable at a heading, cost) with the start, goal, and trajectory over it.  Pick the layer with the radio buttons or the up/down keys; toggle the trajectory and the grid with the checkboxes or `t` and `g`; pick the heading bin of the heading layer with the slider or the left/right keys, and a compass arrow shows that heading (keys set in `plot.*_key`).
