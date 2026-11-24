"""Tests for the Frontseater base's capability lifecycle: the generic request diff,
ticking before controls, the default describe_status(), and shutdown() -- on a minimal
Frontseater that is nothing but a CAPABILITIES tuple."""
import unittest

from mtofr.core.capability import Capability, ParamSpec
from mtofr.core.state import State
from mtofr.environments.anywhere.hardware import StationaryHardware
from mtofr.platform.frontseater import Frontseater


class _Counter(Capability):
    """Logs every lifecycle call to its Frontseater's `events`, and publishes its tick count."""
    ipl_type = "counter"
    description = "Counts ticks."
    outputs = (ParamSpec("count", int, "ticks so far"),)

    def start(self) -> None:
        """Logs the start and zeroes the count."""
        self.count = 0
        self.frontseater.events.append(("start", self.name))

    def tick(self) -> None:
        """Logs the tick and publishes the count."""
        self.count += 1
        self.frontseater.events.append(("tick", self.name))
        self.write("count", self.count)

    def stop(self) -> None:
        """Logs the stop."""
        self.frontseater.events.append(("stop", self.name))

    def status(self) -> str:
        """E.g. "3 ticks"."""
        return f"{self.count} ticks"


class _CountingFrontseater(Frontseater):
    """Nothing but CAPABILITIES, plus an event log and a compute_controls() that logs when it runs."""
    CAPABILITIES = (_Counter,)

    def __init__(self):
        """A stationary platform with an empty event log."""
        super().__init__(StationaryHardware(State()))
        self.events = []

    def compute_controls(self, state) -> dict:
        """Logs that controls were computed."""
        self.events.append(("controls", None))
        return {}


class _FakeBackseater:
    """Records publishes."""
    def __init__(self):
        """No publishes yet."""
        self.published = []

    def publish(self, database_name: str, key: str, value) -> None:
        """Record the publish."""
        self.published.append((key, value))


def _request(count_key: str = "n") -> dict:
    """A counter capability request publishing to `count_key`."""
    return {"capability": "counter", "inputs": {}, "outputs": {"count": count_key}}


class TestFrontseaterLifecycle(unittest.TestCase):
    def setUp(self):
        """A _CountingFrontseater wired to a recording fake backseater."""
        self.frontseater = _CountingFrontseater()
        self.frontseater.backseater = _FakeBackseater()

    def test_capabilities_come_from_the_capabilities_tuple(self):
        """capabilities() advertises every class in CAPABILITIES."""
        self.assertIs(self.frontseater.capabilities().get("counter"), _Counter)

    def test_a_new_request_is_started(self):
        """A request name not running yet is started."""
        self.frontseater.set_active_capabilities({"a": _request()})
        self.assertEqual(self.frontseater.events, [("start", "a")])

    def test_a_gone_request_is_stopped(self):
        """A running request name missing from the new dict is stopped."""
        self.frontseater.set_active_capabilities({"a": _request()})
        self.frontseater.set_active_capabilities({})
        self.assertEqual(self.frontseater.events[-1], ("stop", "a"))

    def test_an_equal_request_keeps_running(self):
        """A request equal to the running one (even a different dict object) is left alone."""
        self.frontseater.set_active_capabilities({"a": _request()})
        self.frontseater.set_active_capabilities({"a": _request()})
        self.assertEqual(self.frontseater.events, [("start", "a")])

    def test_a_changed_request_is_restarted(self):
        """A same-named request with different bindings is stopped, then started fresh."""
        self.frontseater.set_active_capabilities({"a": _request("n")})
        self.frontseater.set_active_capabilities({"a": _request("m")})
        self.assertEqual(self.frontseater.events, [("start", "a"), ("stop", "a"), ("start", "a")])

    def test_an_unknown_capability_raises(self):
        """A request for a capability not in CAPABILITIES raises ValueError."""
        with self.assertRaises(ValueError):
            self.frontseater.set_active_capabilities({"x": {"capability": "fly", "inputs": {}, "outputs": {}}})

    def test_capabilities_tick_before_controls(self):
        """begin_update() ticks every running capability, then computes controls."""
        self.frontseater.set_active_capabilities({"a": _request()})
        self.frontseater.update()
        self.assertEqual(self.frontseater.events[1:], [("tick", "a"), ("controls", None)])
        self.assertEqual(self.frontseater.backseater.published, [("n", 1)])

    def test_describe_status_defaults(self):
        """describe_status() is "idle" with nothing running, else a count plus each capability's status()."""
        self.assertEqual(self.frontseater.describe_status(), {"overall": "idle", "capabilities": {}})
        self.frontseater.set_active_capabilities({"a": _request()})
        self.frontseater.tick_capabilities()
        self.assertEqual(self.frontseater.describe_status(),
                         {"overall": "1 capability request(s) active", "capabilities": {"a": "1 ticks"}})

    def test_shutdown_stops_every_running_capability(self):
        """shutdown() stops everything still running."""
        self.frontseater.set_active_capabilities({"a": _request("n"), "b": _request("m")})
        self.frontseater.shutdown()
        self.assertEqual(sorted(event for event in self.frontseater.events if event[0] == "stop"),
                         [("stop", "a"), ("stop", "b")])

    def test_default_controls_are_the_hardwares_idle_controls(self):
        """The base compute_controls() returns the Hardware's idle_controls."""
        self.assertEqual(Frontseater(StationaryHardware(State())).compute_controls(State()), {})


if __name__ == "__main__":
    unittest.main()
