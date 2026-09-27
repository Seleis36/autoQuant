"""Shared matplotlib styling for crypto-alts report figures (validated categorical palette,
recessive chrome, text in ink tokens; lines are direct-labelled because slots 3-5 are < 3:1
against the surface)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def setup():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "font.size": 10, "axes.titlesize": 12, "axes.titlecolor": INK,
        "axes.titleweight": "bold", "legend.frameon": False, "legend.labelcolor": INK2, "lines.linewidth": 1.8,
    })


def end_label(ax, x, y, text, color, dy=0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points", va="center", fontsize=9, color=INK2)
    ax.plot([x], [y], "o", ms=4, color=color)


def end_labels(ax, items, min_gap_frac=0.045):
    """Direct labels at line ends, nudged apart vertically so they never collide.
    items: list of (x, y, text, color)."""
    lo, hi = ax.get_ylim(); gap = (hi - lo) * min_gap_frac
    items = sorted(items, key=lambda t: t[1])
    placed = []
    for x, y, text, color in items:
        yy = y if not placed else max(y, placed[-1] + gap)
        placed.append(yy)
        ax.plot([x], [y], "o", ms=4, color=color)
        ax.annotate(text, (x, y), xytext=(x, yy), textcoords="data", va="center", fontsize=9, color=INK2,
                    xycoords="data", ha="left")
