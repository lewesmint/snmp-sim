"""Common utilities shared across UI modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tkinter as tk
    from collections.abc import Callable


class Logger:
    """Simple logger that outputs to both console and optional text widget with color coding."""

    def __init__(self, log_widget: tk.Text | None = None) -> None:
        self.log_widget = log_widget
        self._tags_configured = False

    def _configure_tags(self) -> None:
        """Configure color tags for different log levels."""
        if not self.log_widget or self._tags_configured:
            return

        try:
            # Configure tags for different log levels
            self.log_widget.tag_config("ERROR", foreground="#ff4444")  # Red
            self.log_widget.tag_config("WARNING", foreground="#ff9933")  # Orange
            self.log_widget.tag_config("INFO", foreground="")  # Default color
            self.log_widget.tag_config("DEBUG", foreground="#888888")  # Gray
            self._tags_configured = True
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            pass

    def log(self, message: str, level: str = "INFO") -> None:
        """Log a message with timestamp and level, with color coding."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}\n"

        # Print to stdout

        # Append to GUI log area if available
        if self.log_widget:
            try:
                self._configure_tags()
                self.log_widget.configure(state="normal")

                # Insert with appropriate tag for color
                self.log_widget.insert("end", log_entry, level)

                self.log_widget.see("end")
                self.log_widget.configure(state="disabled")
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                # If log area not available, just print
                pass

    def set_log_widget(self, widget: tk.Text) -> None:
        """Update the log widget."""
        self.log_widget = widget
        self._tags_configured = False  # Reset tag configuration for new widget


def save_gui_log(log_widget: tk.Text, filename: str = "gui.log") -> None:
    """Save GUI log content to file."""
    try:
        logs_dir = Path("logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / filename
        with open(log_path, "w", encoding="utf-8") as f:
            try:
                text = log_widget.get("1.0", "end")
                f.write(text)
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                pass
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        pass


def format_snmp_value(value: Any) -> str:
    """Format SNMP value for display."""
    try:
        # Try to prettyPrint if available (pysnmp objects)
        if hasattr(value, "prettyPrint"):
            result = value.prettyPrint()
            return str(result)
        return str(value)
    except (AttributeError, LookupError, OSError, TypeError, ValueError):
        return str(value)


def safe_call(
    func: Callable[..., Any],
    default: Any = None,
    logger: Logger | None = None,
) -> Any:
    """Safely call a function and log errors if logger is provided."""
    try:
        return func()
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        if logger:
            logger.log(f"Error in {func.__name__}: {e}", "ERROR")
        return default
