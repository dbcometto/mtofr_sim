# Checklists

What a developer does to extend the sim: a new capability, platform, environment, Knowledge type, or scenario.  The target is the ROS-node feel, where the user writes their own functions as callbacks and the framework hides the plumbing.  Remaining **Friction:** notes mark what still falls short; the [summary](#friction-summary) tracks every friction item, resolved or not.

Paths are under `src/mtofr/` unless they start with `tests/` or `docs/`.  The reference implementations are `BicycleFrontseater` (`environments/ground_plane/platforms/bicycle_ugv/`), which runs per-tick capabilities, and `MissionEditorFrontseater` (`environments/ground_plane/platforms/interface/`), which runs on/off capabilities.



## 1. New Capability

A capability is one `Capability` subclass: class attributes declare it, and its methods run it.  The Frontseater base creates one instance per running capability request and calls `start()` once, `tick()` every sim tick (before controls are computed), and `stop()` once.  A request whose bindings change is restarted, and an equal request across a node change keeps running.

```python
class MoveTo(Capability):
    """Steers the MPC toward a target until within tolerance."""
    ipl_type = "move_to"
    description = "Navigate to a target location until within tolerance, using the internal MPC."
    inputs = (ParamSpec("target", Location, "Location to navigate to"),
              ParamSpec("tolerance", float, "Distance within which the target counts as reached, in meters"))
    outputs = (ParamSpec("arrived", bool, "True once within tolerance of the current target"),)

    def start(self) -> None:
        self.arrived = False

    def tick(self) -> None:
        target, tolerance = self.read("target"), self.read("tolerance")
        self.frontseater.navigation_target = target
        state = self.hardware.read_state()
        self.arrived = bool(np.hypot(state.x - target.x, state.y - target.y) <= tolerance)
        self.write("arrived", self.arrived)

    def stop(self) -> None:
        self.frontseater.navigation_target = None

    def status(self) -> str:
        return "arrived" if self.arrived else "en route"
```

- [ ] **Pick its home** by what it needs:
  - `platform/common_capabilities.py` if it needs only `read_state().t` (e.g. `Stopwatch`);
  - `environments/<environment>/capabilities.py` if it needs only that environment's State (e.g. `SensePose`);
  - `environments/<environment>/platforms/<type>/capabilities.py` if it drives one platform's internals (e.g. `MoveTo`, `Avoid`).
- [ ] **Declare it:** `ipl_type`, `description`, and `inputs`/`outputs` as `ParamSpec(name, type, description)`.  Every field binds to a Knowledge key of exactly that type; there are no literals.  A new type needs [§4](#4-new-knowledge-type).
- [ ] **Implement only the methods it needs**; each defaults to doing nothing (`status()` defaults to `"running"`):
  - `start()`: set up instance attributes;
  - `tick()`: the work;
  - `stop()`: undo anything it set on the Frontseater;
  - `status()`: a short display string.
- [ ] **Do the I/O through two methods:**
  - `self.read("field")` queries the bound key live, every call, so a retargeted key is seen next tick;
  - `self.write("field", value)` publishes if the request bound that output, and does nothing otherwise.
  - Both raise `KeyError` for a field the capability doesn't declare.
  - `self.hardware` and `self.frontseater` are available, plus `self.frontseater.backseater` for anything beyond the bindings.
- [ ] **Actuate it** (only if it moves the platform) by setting a Frontseater attribute that `compute_controls()`/`begin_controls()` reads (e.g. `navigation_target`).
  - **Friction (remaining, 5):** that attribute is ad hoc per platform, and nothing arbitrates between concurrent requests (with two `move_to`, the last ticked wins).
- [ ] **List it** in the Frontseater's `CAPABILITIES` tuple.  The Backseater's bind check, gossip, the web editor, and the LLM assistant all read the registry built from it.
- [ ] **Use it:** declare the bound keys in a mission graph's `"knowledge"` and add the request to a node, in a scenario file or the web editor.
- [ ] **Test it** through the Frontseater's `set_active_capabilities()` and `tick_capabilities()`, with a fake backseater (see `tests/test_bicycle_frontseater.py`).  Register `addCleanup(frontseater.shutdown)` for a Frontseater with a worker process.  Update `docs/spec.md`.



## 2. New Platform (Hardware + Frontseater) in an Existing Environment

The new platform goes in a folder, `environments/<environment>/platforms/<type>/`, holding:
- `__init__.py`
- `hardware.py`
- `frontseater.py`
- `spec.py`
- `capabilities.py` if it has its own
- helpers (e.g. `dynamics.py`)

### Hardware (`hardware.py`)
- [ ] **Pick a base.**
  - The environment's Hardware base, e.g. `GroundPlaneHardware`.  Implement the pure `calculate_dynamics(state, controls, dt, max_speed_multiplier)`.  The inherited `step_dynamics()` applies the terrain; override it only for a different terrain response.
  - Or `Hardware` directly.  Declare `environment_type` (an `Environment` class, or `None` for any) and implement `step_dynamics(dt, environment)`, the one place Hardware sees the Environment (cf. `ConsoleHardware`, which never moves and samples a `GroundMapSensor` there).
- [ ] **Set `idle_controls`** (the "do nothing" controls dict) as a class attribute.  The base starts with it, and an idle Frontseater sends it.
- [ ] **Write `__init__`.**  Call `super().__init__(sensor)` (`PerfectSensor` by default) and set `self.state = initial_state or <EnvironmentState>()`.  Physical limits go in the Config section as constants.
- [ ] **Document the controls dict** (its keys and units) in the class docstring.
  - **Friction (remaining, 5):** controls are an untyped dict whose contract is a docstring.

### Frontseater (`frontseater.py`)
- [ ] **Subclass `Frontseater`** and list `CAPABILITIES = (...)`.  For a platform that never moves, that's the whole class.
- [ ] **If it has its own state or resources,** write an `__init__` that calls `super().__init__(hardware, debug)` first.
- [ ] **If it moves,** do one of:
  - override `compute_controls(state) -> dict`, which runs synchronously each tick after the capabilities;
  - for expensive work, override `begin_controls()` (dispatch, e.g. to a worker process) and `finish_controls()` (collect and `send_controls`), so platforms overlap.  A worker process brings the `__main__` guard in `main.py` and the explicit test-cleanup rule (`docs/style.md`).
- [ ] **Optional overrides:**
  - `default_mission_graph()`: the safe idle the platform boots into (the base gives an inert `"startup"` node).  Prefix its keys with `self.platform_id` (see Known Issues in the roadmap).
  - `attach(world, window_root)`: setup that needs `World` or the Tk root.
  - `shutdown()`: release your own resources, after calling `super().shutdown()`, which stops every running capability.

### Spec factory (`spec.py`)
- [ ] **Write the factory**, `<type>(platform_id, <placement>, mission_graph=None, privilege_level=DEFAULT_PRIVILEGE_LEVEL) -> PlatformSpec`.  A nested `build_frontseater(debug)` closure builds the Hardware, then the Frontseater:
  ```python
  def my_platform(platform_id, start_x, start_y, mission_graph=None, privilege_level=DEFAULT_PRIVILEGE_LEVEL):
      def build_frontseater(debug=False):
          hardware = MyHardware(initial_state=GroundPlaneState(x=start_x, y=start_y))
          return MyFrontseater(hardware=hardware, debug=debug)
      return PlatformSpec(platform_id=platform_id, build_frontseater=build_frontseater,
                          mission_graph=mission_graph, privilege_level=privilege_level)
  ```
  - **Friction (remaining, minor):** the same closure boilerplate is repeated for every platform type (left as is: it is short and explicit).

### Wire-up
- [ ] **Add the spec** to a scenario's `platforms` list.  `World` refuses it at construction if `environment_type` or the State type doesn't match.
- [ ] **Test it:** Hardware dynamics in `tests/test_<type>_hardware.py`, the Frontseater in `tests/test_<type>_frontseater.py` (with cleanup), and that `World` accepts the platform.  Add it under "Environments, Maps, Platform Types" in `docs/spec.md`.



## 3. New Environment

The new environment goes in `environments/<environment>/`, holding:
- `__init__.py`, whose docstring states the layer rule
- `state.py`
- `env.py`
- `hardware.py`
- `capabilities.py` (optional)
- `sensors/`
- `maps/` (optional)
- `viz/`
- `platforms/`

- [ ] **State** (`state.py`): a `@dataclass` subclass of `State` with every tracked field, units and frame commented inline.
- [ ] **Environment** (`env.py`): an `Environment` subclass that declares `state_type = <EnvironmentState>` and exposes only passive query methods the vehicles need (cf. `GroundPlaneEnv.is_blocked()`, `speed_multiplier_at()`).  It never steps anything.
- [ ] **Hardware base** (`hardware.py`): a `Hardware` subclass with `environment_type = <Environment>`.  It has a default `step_dynamics()` that queries the environment around a pure abstract hook for the vehicle's own dynamics (cf. `GroundPlaneHardware`).
- [ ] **Shared capabilities** (`capabilities.py`, optional): anything every platform here can run from this State alone (cf. `SensePose`).
- [ ] **Sensors** (`sensors/`, optional): `Sensor` subclasses implementing `read(state) -> State`, plus anything that reads the Environment itself (cf. `GroundMapSensor.read(environment)`), sampled in a Hardware's `step_dynamics()`.
- [ ] **Viewer** (`viz/`): an `EnvironmentViewer` subclass.  Implement `configure_ax(ax)` and `render(ax, states, selected_id, show_traversability, show_regions)`, and set `background_color`.  Add a `for_environment(environment)` classmethod for the scenario's `build_viewer`.
  - **Friction (remaining, 7):** the viewer interface and the dashboard's checkboxes have ground-plane map overlays baked in, and only 2D matplotlib Axes are supported.
- [ ] **Platforms:** at least one platform type per [§2](#2-new-platform-hardware--frontseater-in-an-existing-environment).  The `interface` platform is a ground_plane platform (it senses the ground map), so a new environment needs its own operator-console platform to have a mission editor.
- [ ] **Scenario** per [§5](#5-new-scenario).
- [ ] **Check the known leaks** (friction 7, remaining):
  - `Location`, `Pose`, and `Trajectory` are 2D world-frame types.  An environment with different geometry needs its own types ([§4](#4-new-knowledge-type)).
- [ ] **Test** the State, Environment queries, Hardware base, and viewer (`TK_AVAILABLE` guard where Tk is needed).  Add the environment's own bullet in `docs/spec.md`.



## 4. New Knowledge Type

- [ ] **Add one file**, `database/knowledge_types/<type_name>.py`, with a `KnowledgeEntry` subclass.  Every module in that package is imported automatically, and the subclass registers itself in `KNOWLEDGE_TYPES_BY_NAME` under its class name.  That makes it declarable, editable, and saveable.
  - `__init__` takes only `bool`/`float`/`int`/`str`-annotated parameters and stores each as a same-named attribute.  `constructor_fields()` introspects the signature to build the editor forms and the JSON encoding.
  - Add a `describe()` classmethod (plaintext for a human or LLM) and a `__repr__`.
  - The class name must be unique; a second class with a taken name raises `ValueError`.
- [ ] **Re-export** it from `database/__init__.py` (and `knowledge_types/__init__.py`) only if code imports it by name, as with `Location` and `Pose`.
- [ ] **Note:** there is no `__eq__`, so an edge condition on a compound type can only use `is None` / `is not None`.
- [ ] **Test** a save/load round-trip in `tests/test_mission_serialization.py`.



## 5. New Scenario

- [ ] **Add one file**, `scenarios/<name>.py`.  Its docstring says what it exercises.  It holds its mission graphs (named `mission_<scenario>_<platform_id>`) and `SCENARIO = ScenarioConfig(build_environment, build_viewer, platforms)`.  It is discovered into `SCENARIOS["<name>"]` automatically.
- [ ] **Run it** by setting `ACTIVE_SCENARIO = "<name>"` in `main.py`.



## Friction Summary

The ROS-node target: the user writes their own functions and hooks them to callbacks, timers, and pub/sub, and the framework hides the plumbing.
1. **Resolved: a capability is one unit.**  Its declaration and its `start`/`tick`/`stop`/`status` callbacks live in one `Capability` class, instead of a registry entry plus four `if/elif` chains.
2. **Resolved: I/O is resolved for you.**  `read()`/`write()` follow the request's bindings, replacing `query(inputs[...])` and `if field in outputs` guards.
3. **Resolved: the lifecycle lives in the base.**  The `Frontseater` base owns the request diff, the instances, ticking (always before controls), the default status, and stopping on shutdown.
4. **Resolved: `shutdown()` is on the base**, defaulting to stopping every running capability.
5. **Remaining: actuation is ad hoc.**  Capabilities that move the platform set plain Frontseater attributes, with no arbitration between concurrent requests, and the controls dict is untyped.  Idle controls are now declared once, on the Hardware.
6. **Resolved: registration is automatic** for Knowledge types (one file each) and scenarios (one file each).  The `spec.py` closure per platform remains (minor).
7. **Remaining: environment assumptions leak upward:** the ground-plane overlay flags in `EnvironmentViewer` and the dashboard, and 2D world-frame `Location`/`Pose`/`Trajectory`.  (`describe_world()` is no longer a leak: the interface is now a ground_plane platform.)
