"""Tests that EnvironmentViewer enforces its interface contract."""
import unittest

from mtofr.viz.base import EnvironmentViewer


class TestEnvironmentViewer(unittest.TestCase):
    def test_cannot_instantiate_without_implementing_abstract_methods(self):
        """A subclass that leaves configure_ax/render abstract raises TypeError on instantiation."""
        with self.assertRaises(TypeError):
            class IncompleteViewer(EnvironmentViewer):
                pass
            IncompleteViewer()

    def test_subclass_implementing_both_methods_can_be_instantiated(self):
        """A subclass implementing configure_ax and render instantiates without error."""
        class CompleteViewer(EnvironmentViewer):
            def configure_ax(self, ax):
                """Leave the Axes untouched."""
                pass

            def render(self, ax, states, selected_id=None):
                """Draw nothing."""
                pass

        CompleteViewer()   # should not raise


if __name__ == "__main__":
    unittest.main()
