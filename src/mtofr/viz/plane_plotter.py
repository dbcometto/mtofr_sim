"""A 2D plot for platforms on a plane"""
import numpy as np
import matplotlib.pyplot as plt


class PlanePlotter:
    """Vizualize platforms on a 2D plane"""
    def __init__(self, xlim=(-10, 10), ylim=(-10, 10), arrow_len=0.5):
        plt.ion()
        self.fig, self.ax = plt.subplots()
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        self.ax.set_aspect("equal")
        self.arrow_len = arrow_len
        self.markers = {}   # eid -> dot artist
        self.arrows = {}    # eid -> heading arrow artist

    def update(self, states: dict):
        """Draw the plane"""
        for eid, state in states.items():
            if eid not in self.markers:
                (marker,) = self.ax.plot([], [], "o", label=eid)
                self.markers[eid] = marker
                self.ax.legend()

            self.markers[eid].set_data([state.x], [state.y])

            dx = self.arrow_len * np.cos(state.theta)
            dy = self.arrow_len * np.sin(state.theta)

            if eid in self.arrows:
                self.arrows[eid].remove()
            self.arrows[eid] = self.ax.arrow(
                state.x, state.y, dx, dy,
                head_width=0.15, length_includes_head=True, color="black"
            )

        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()