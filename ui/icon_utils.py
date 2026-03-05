"""Shared icon helpers for UI tree views."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path

IconSpecs = dict[str, tuple[str, str | None]]


def make_generated_icon(
    *,
    size: int,
    color: str,
    inner: str | None,
    inner_padding: int,
) -> tk.PhotoImage:
    """Create a simple generated square icon."""
    image = tk.PhotoImage(width=size, height=size)
    for x in range(size):
        for y in range(size):
            image.put(color, (x, y))

    if inner:
        start = inner_padding
        end = size - inner_padding
        for x in range(start, end):
            for y in range(start, end):
                image.put(inner, (x, y))

    return image


def load_icons_with_fallback(
    *,
    icons_dir: Path,
    icon_specs: IconSpecs,
    size: int = 16,
    inner_padding: int = 4,
) -> dict[str, tk.PhotoImage]:
    """Load PNG icons from disk with generated-icon fallback."""
    icons: dict[str, tk.PhotoImage] = {}

    for name, (color, inner) in icon_specs.items():
        try:
            png_path = icons_dir / f"{name}.png"
            if png_path.exists():
                icons[name] = tk.PhotoImage(file=str(png_path))
            else:
                icons[name] = make_generated_icon(
                    size=size,
                    color=color,
                    inner=inner,
                    inner_padding=inner_padding,
                )
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            icons[name] = make_generated_icon(
                size=size,
                color=color,
                inner=inner,
                inner_padding=inner_padding,
            )

    return icons
