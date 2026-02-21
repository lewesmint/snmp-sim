from __future__ import annotations

import logging
import logging.handlers
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    log_dir: Path
    log_file: str = "snmp-agent.log"
    console: bool = True
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    rotate_on_startup: bool = True


if TYPE_CHECKING:
    from app.app_config import AppConfig


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds color to log levels for console output."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Save the original levelname
        original_levelname = record.levelname

        # Add color to the levelname
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )

        # Format the record
        result = super().format(record)

        # Restore the original levelname
        record.levelname = original_levelname

        return result


class FlushingStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Stream handler that flushes after every emit."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)


class FlushingRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Rotating file handler that flushes after every emit."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
            self.flush()
        except Exception:
            self.handleError(record)


def _archive_log_file(log_path: Path) -> None:
    """
    Archive an existing log file by moving it to the archive subdirectory with a timestamp.

    If the log file exists, reads the first line to extract the timestamp and moves
    the file to logs/archive/ with the timestamp in the filename. If no timestamp can
    be extracted, uses the file's modification time.

    Args:
        log_path: Path to the log file to archive
    """
    if not log_path.exists():
        return

    # Try to read the first line to get the timestamp
    timestamp_str = None
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            # Match timestamp format: YYYY-MM-DD HH:MM:SS.mmm
            match = re.match(
                r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3}", first_line
            )
            if match:
                timestamp_str = match.group(1)
    except Exception:
        # If we can't read the file, we'll use the modification time
        pass

    # If we couldn't extract timestamp from first line, use file modification time
    if timestamp_str is None:
        mtime = log_path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime)
        timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S")

    # Convert timestamp to filename-safe format: YYYY-MM-DD_HH-MM-SS
    filename_timestamp = timestamp_str.replace(" ", "_").replace(":", "-")

    # Create archive directory if it doesn't exist
    log_dir = log_path.parent
    archive_dir = log_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Create archived filename
    log_name = log_path.stem
    log_ext = log_path.suffix
    archived_name = f"{log_name}_{filename_timestamp}{log_ext}"
    archived_path = archive_dir / archived_name

    # If archived file already exists, add a counter
    counter = 1
    while archived_path.exists():
        archived_name = f"{log_name}_{filename_timestamp}_{counter}{log_ext}"
        archived_path = archive_dir / archived_name
        counter += 1

    # Move the file
    try:
        shutil.move(str(log_path), str(archived_path))
    except Exception:
        # If move fails, just continue - we'll append to the existing file
        pass


class AppLogger:
    _configured: bool = False

    @staticmethod
    def configure(app_config: "AppConfig") -> None:
        """
        Configure logging from an AppConfig instance.
        """
        from typing import cast

        logger_cfg = cast(dict[str, Any], app_config.get("logger", {}))
        import os

        log_dir = logger_cfg.get("log_dir", "logs")
        log_file = logger_cfg.get("log_file", "snmp-agent.log")
        level = logger_cfg.get("level", "INFO")
        console = logger_cfg.get("console", True)
        max_bytes = logger_cfg.get("max_bytes", 10 * 1024 * 1024)
        backup_count = logger_cfg.get("backup_count", 5)
        rotate_on_startup = logger_cfg.get("rotate_on_startup", True)
        config = LoggingConfig(
            level=level,
            log_dir=Path(os.path.abspath(log_dir)),
            log_file=log_file,
            console=console,
            max_bytes=max_bytes,
            backup_count=backup_count,
            rotate_on_startup=rotate_on_startup,
        )
        AppLogger(config)

    def __init__(self, config: LoggingConfig) -> None:
        if AppLogger._configured:
            return
        self._configure(config)
        AppLogger._configured = True

    @staticmethod
    def get(name: str | None = None) -> logging.Logger:
        return logging.getLogger(name)

    @staticmethod
    def warning(msg: str, *args: Any, **kwargs: Any) -> None:
        logging.getLogger().warning(msg, *args, **kwargs)

    @staticmethod
    def error(msg: str, *args: Any, **kwargs: Any) -> None:
        logging.getLogger().error(msg, *args, **kwargs)

    @staticmethod
    def info(msg: str, *args: Any, **kwargs: Any) -> None:
        logging.getLogger().info(msg, *args, **kwargs)

    @staticmethod
    def _configure(config: LoggingConfig) -> None:
        level_name = config.level.upper()
        level = logging._nameToLevel.get(level_name, logging.INFO)

        config.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = config.log_dir / config.log_file

        # Archive existing log file if rotation is enabled
        if config.rotate_on_startup:
            _archive_log_file(log_path)

        root = logging.getLogger()
        root.setLevel(level)

        for handler in list(root.handlers):
            root.removeHandler(handler)

        fmt = (
            "%(asctime)s.%(msecs)03d "
            "%(levelname)s "
            "%(name)s "
            "[%(threadName)s] "
            "%(message)s"
        )
        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")

        file_handler = FlushingRotatingFileHandler(
            filename=log_path,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

        if config.console:
            console_handler = FlushingStreamHandler(sys.stdout)
            console_handler.setLevel(level)
            # Use colored formatter for console output
            colored_formatter = ColoredFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
            console_handler.setFormatter(colored_formatter)
            root.addHandler(console_handler)

        AppLogger._suppress_third_party_loggers(level)

    @staticmethod
    def _suppress_third_party_loggers(level: int) -> None:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.error").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.WARNING)

        # Only suppress pysnmp loggers if not in DEBUG mode
        if level > logging.DEBUG:
            logging.getLogger("pysnmp").setLevel(logging.WARNING)
        else:
            # Enable pysnmp logging at DEBUG level
            logging.getLogger("pysnmp").setLevel(logging.DEBUG)
