"""Shared matplotlib style for rates-bonds research figures.

Light surface, text in ink tokens (never in the series colour), hairline grid, 2 px lines,
categorical hues in a fixed order (blue, orange, aqua -- validated as a set for colour-vision
separation; aqua is below 3:1 contrast on the surface, so any chart using it also carries a
direct label or a legend).
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
NEUTRAL = "#8a8983"


def apply():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "lines.linewidth": 2.0, "lines.solid_capstyle": "round", "lines.solid_joinstyle": "round",
        "legend.frameon": False, "legend.fontsize": 9, "font.size": 10,
        "axes.axisbelow": True, "figure.dpi": 130,
    })


def end_label(ax, x, y, text, dx=6):
    """Direct label at a line's end, in ink."""
    ax.annotate(text, xy=(x, y), xytext=(dx, 0), textcoords="offset points", va="center",
                ha="left", fontsize=9, color=INK2, annotation_clip=False)


def subtitle(ax, text):
    ax.text(0.0, 1.02, text, transform=ax.transAxes, fontsize=9, color=INK2, va="bottom", ha="left")
