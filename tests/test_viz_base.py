"""Tests that EnvironmentViewer enforces its interface contract."""
import unittest

from mtofr.viz.base import EnvironmentViewer


class TestEnvironmentViewer(unittest.TestCase):
    def test_cannot_instantiate_without_implementing_abstract_methods(self):
        with self.assertRaises(TypeError):
            class IncompleteViewer(EnvironmentViewer):
                pass
            IncompleteViewer()

    def test_subclass_implementing_both_methods_can_be_instantiated(self):
        class CompleteViewer(EnvironmentViewer):
            def configure_ax(self, ax):
                pass

            def render(self, ax, states, selected_id=None):
                pass

        CompleteViewer()   # should not raise


if __name__ == "__main__":
    unittest.main()
