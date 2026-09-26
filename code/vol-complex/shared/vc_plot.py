"""Matplotlib house style for vol-complex report figures (reference palette, light surface)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # categorical slots 1-4, fixed order
NEUTRAL = "#9a9892"


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.6,
        "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "legend.frameon": False,
        "figure.dpi": 130,
    })


def direct_label(ax, series, text, color):
    """Label the last point of a line with its series name (text in secondary ink)."""
    s = series.dropna()
    ax.plot([s.index[-1]], [s.iloc[-1]], "o", ms=4, color=color)
    ax.annotate(text, (s.index[-1], s.iloc[-1]), xytext=(4, 0), textcoords="offset points",
                va="center", fontsize=8, color=INK2)
