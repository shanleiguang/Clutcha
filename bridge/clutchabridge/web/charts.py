"""Server-side SVG charts: no chart library, no network, no build step."""

from __future__ import annotations

from html import escape

WIDTH = 640


def _fmt(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    if value >= 10 or float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


def empty(text: str) -> str:
    return f'<div class="empty">{escape(text)}</div>'


def grouped_bars(labels: list[str], series: list[tuple[str, list[float]]], colors: list[str],
                 height: int = 150, every: int = 6) -> str:
    """Vertical grouped bars, one group per label."""
    if not labels or not series:
        return empty("No data yet")
    values = [value for _, points in series for value in points]
    top = max(values) if values else 0
    if top <= 0:
        return empty("No data yet")

    pad_l, pad_r, pad_t, pad_b = 34, 10, 12, 20
    plot_w = WIDTH - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    group_w = plot_w / len(labels)
    count = max(1, len(series))
    bar_w = max(1.5, group_w * 0.7 / count)

    parts = [
        f'<svg viewBox="0 0 {WIDTH} {height}" role="img">',
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{WIDTH - pad_r}" y2="{pad_t + plot_h}" '
        f'stroke="var(--border)"/>',
        f'<text x="{pad_l - 8}" y="{pad_t + 8}" fill="var(--dim)" font-size="10" text-anchor="end">'
        f'{_fmt(top)}</text>',
        f'<text x="{pad_l - 8}" y="{pad_t + plot_h}" fill="var(--dim)" font-size="10" '
        f'text-anchor="end">0</text>',
    ]
    for index, label in enumerate(labels):
        if index % every and index != len(labels) - 1:
            continue
        x = pad_l + group_w * index + group_w / 2
        parts.append(
            f'<text x="{x:.1f}" y="{height - 6}" fill="var(--dim)" font-size="10" '
            f'text-anchor="middle">{escape(label)}</text>'
        )
    for series_index, (_, points) in enumerate(series):
        color = colors[series_index % len(colors)]
        for index, value in enumerate(points):
            if value <= 0:
                continue
            bar_h = max(1.5, plot_h * value / top)
            x = pad_l + group_w * index + group_w * 0.15 + bar_w * series_index
            y = pad_t + plot_h - bar_h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'rx="2" fill="{color}"><title>{escape(labels[index])}: {_fmt(value)}</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def legend(items: list[tuple[str, str]]) -> str:
    return "".join(
        f'<span><i style="background:{color}"></i>{escape(name)}</span>' for name, color in items
    )
