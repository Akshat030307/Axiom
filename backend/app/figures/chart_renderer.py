"""ChartSpec -> PNG bytes via matplotlib (PRD §11.1). The LLM never emits
plotting code — only the validated data+type in ChartSpec — this module is
the only thing that touches a plotting library. Agg backend: headless,
no display server needed in the container.

One rendered variant, not the PRD's dark/light pair — "charts alone
demonstrate the pattern" was the brief for this build; a white background
prints cleanly and reads fine as an embedded card in the app's dark UI.
"""

import io
import textwrap

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402  (must follow matplotlib.use)

from app.models.schemas import ChartSpec

_FIGSIZE = (8.0, 4.6)
_DPI = 150
_MAX_TICK_LABEL_CHARS = 28


def _shorten(label: str, limit: int = _MAX_TICK_LABEL_CHARS) -> str:
    """The prompt asks for short category labels, but a model that ignores
    that shouldn't be able to produce an unreadable, clipped chart — long
    labels are truncated with an ellipsis rather than trusted verbatim."""
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def _apply_categorical_axis(ax, categories: list[str], horizontal: bool) -> None:
    positions = range(len(categories))
    labels = [_shorten(c) for c in categories]
    if horizontal:
        ax.set_yticks(list(positions))
        ax.set_yticklabels(labels, fontsize=8)
    else:
        ax.set_xticks(list(positions))
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)


def _draw(ax, spec: ChartSpec) -> None:
    x = list(range(len(spec.categories)))

    if spec.chart_type == "bar":
        ax.bar(x, spec.series[0].values)
        _apply_categorical_axis(ax, spec.categories, horizontal=False)
    elif spec.chart_type == "horizontal_bar":
        ax.barh(x, spec.series[0].values)
        _apply_categorical_axis(ax, spec.categories, horizontal=True)
    elif spec.chart_type == "grouped_bar":
        n = max(len(spec.series), 1)
        width = 0.8 / n
        for i, s in enumerate(spec.series):
            offsets = [xi + i * width - 0.4 + width / 2 for xi in x]
            ax.bar(offsets, s.values, width=width, label=s.name)
        _apply_categorical_axis(ax, spec.categories, horizontal=False)
        ax.legend(fontsize=8)
    elif spec.chart_type == "line":
        for s in spec.series:
            ax.plot(x, s.values, marker="o", label=s.name)
        _apply_categorical_axis(ax, spec.categories, horizontal=False)
        if len(spec.series) > 1:
            ax.legend(fontsize=8)
    elif spec.chart_type == "stacked_area":
        ax.stackplot(x, *[s.values for s in spec.series], labels=[s.name for s in spec.series])
        _apply_categorical_axis(ax, spec.categories, horizontal=False)
        ax.legend(fontsize=8)
    elif spec.chart_type == "scatter":
        for s in spec.series:
            ax.scatter(x, s.values, label=s.name)
        _apply_categorical_axis(ax, spec.categories, horizontal=False)
        if len(spec.series) > 1:
            ax.legend(fontsize=8)
    elif spec.chart_type == "pie":
        ax.pie(spec.series[0].values, labels=spec.categories, autopct="%1.0f%%", textprops={"fontsize": 8})
        ax.axis("equal")
    else:
        raise ValueError(f"unsupported chart_type: {spec.chart_type}")

    if spec.chart_type != "pie":
        ax.grid(axis="y", alpha=0.25)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)


def render_chart_png(spec: ChartSpec) -> bytes:
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    try:
        _draw(ax, spec)
        wrapped_title = "\n".join(textwrap.wrap(spec.title, width=55)) or spec.title
        ax.set_title(wrapped_title, fontsize=12, fontweight="bold")
        if spec.x_label:
            ax.set_xlabel(spec.x_label, fontsize=9)
        if spec.y_label:
            ax.set_ylabel(spec.y_label, fontsize=9)
        if spec.source_note:
            # Below the figure's own origin, not just near it — rotated
            # category-axis labels extend well past y=0 in figure
            # coordinates, and bbox_inches="tight" (below) expands the saved
            # canvas around whatever it finds, so placing this too close
            # overlapped the labels on a real long-label chart.
            fig.text(0.0, -0.22, spec.source_note, fontsize=7, color="#666666", ha="left", va="top")

        buf = io.BytesIO()
        # bbox_inches="tight" recomputes the actual rendered extent at save
        # time (title, rotated tick labels, legend included) and expands the
        # canvas to fit it — fig.tight_layout() alone was observed clipping
        # long rotated category labels and multi-line titles on a real
        # model-generated spec (see the figures investigation notes).
        fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight", pad_inches=0.35)
        return buf.getvalue()
    finally:
        plt.close(fig)
