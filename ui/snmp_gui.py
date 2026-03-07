# pylint: disable=broad-exception-caught,protected-access,unused-argument
# pylint: disable=unused-variable,attribute-defined-outside-init,line-too-long
# pylint: disable=too-many-lines,missing-module-docstring,missing-class-docstring
# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-statements
# pylint: disable=too-many-branches,too-many-nested-blocks,ungrouped-imports
# pylint: disable=consider-using-dict-items,consider-iterating-dictionary
# pylint: disable=no-else-return,no-else-break,consider-using-max-builtin
# pylint: disable=consider-using-in,import-outside-toplevel,use-maxsplit-arg
# pylint: disable=consider-using-f-string,too-many-return-statements
# pylint: disable=too-many-arguments,too-many-positional-arguments,superfluous-parens
# pylint: disable=too-many-ancestors
# ruff: noqa: ANN401, D100, D107
# ruff: noqa: D401
# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import json
from typing import Any, cast

import customtkinter as ctk
import requests
import yaml

from app.model_paths import GUI_CONFIG_JSON_FILE, GUI_CONFIG_YAML_FILE
from ui.common import Logger
from ui.snmp_gui_connection_mixin import SNMPGuiConnectionMixin
from ui.snmp_gui_dialogs_mixin import SNMPGuiDialogsMixin
from ui.snmp_gui_layout_mixin import SNMPGuiLayoutMixin
from ui.snmp_gui_links_mixin import SNMPGuiLinksMixin
from ui.snmp_gui_oid_tree_instances_mixin import SNMPGuiOidTreeInstancesMixin
from ui.snmp_gui_oid_tree_mixin import SNMPGuiOidTreeMixin
from ui.snmp_gui_search_focus_mixin import SNMPGuiSearchFocusMixin
from ui.snmp_gui_state_preset_mixin import SNMPGuiStatePresetMixin
from ui.snmp_gui_table_edit_mixin import SNMPGuiTableEditMixin
from ui.snmp_gui_table_view_mixin import SNMPGuiTableViewMixin
from ui.snmp_gui_trap_overrides_mixin import SNMPGuiTrapOverridesMixin
from ui.snmp_gui_traps_mixin import SNMPGuiTrapsMixin

# Set appearance mode and color theme
ctk.set_appearance_mode("system")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

class SNMPControllerGUI(
    SNMPGuiLayoutMixin,
    SNMPGuiOidTreeMixin,
    SNMPGuiOidTreeInstancesMixin,
    SNMPGuiSearchFocusMixin,
    SNMPGuiTableViewMixin,
    SNMPGuiTableEditMixin,
    SNMPGuiConnectionMixin,
    SNMPGuiStatePresetMixin,
    SNMPGuiDialogsMixin,
    SNMPGuiLinksMixin,
    SNMPGuiTrapsMixin,
    SNMPGuiTrapOverridesMixin,
):
    """GUI application for controlling SNMP agent with modern tabbed interface."""

    def __init__(self, root: ctk.CTk, api_url: str = "http://127.0.0.1:8800") -> None:
        self.root = root
        self.api_url = api_url
        self.root.title("SNMP Simulator GUI")
        self.root.geometry("900x700")

        self.connected = False
        self.silent_errors = False  # If True, log errors without showing popup dialogs
        self.oids_data: dict[
            str,
            tuple[int, ...],
        ] = {}  # Store OIDs for rebuilding (name -> OID tuple)
        self.oid_values: dict[str, str] = {}  # oid_str -> value
        self.oid_metadata: dict[str, dict[str, Any]] = {}  # oid_str -> metadata
        self.table_instances_data: dict[str, dict[str, Any]] = {}  # Pre-loaded table instances data
        self.table_schemas: dict[str, dict[str, Any]] = {}
        self.oid_to_item: dict[str, str] = {}  # oid_str -> tree item id
        self._pending_oid_focus: dict[str, str | None] | None = None
        self._pending_oid_focus_retries: int = 0
        # Executor for background value fetching
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

        # Initialize logger (will set log widget after UI setup)
        self.logger = Logger()

        self._setup_ui()
        self._log("Application started")

        # Initialize trap-related variables
        self.current_trap_overrides: dict[str, Any] = {}
        self.oid_rows: list[dict[str, Any]] = []

        # Set initial sash position after window is displayed
        self.root.after(100, self._set_initial_sash_position)

        # Bind close handler to save GUI log and config
        with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _log(self, message: str, level: str = "INFO") -> None:
        self.logger.log(message, level)

def _build_main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--autoconnect", action="store_true")
    parser.add_argument(
        "--connect-delay",
        type=int,
        default=0,
        help="Delay in seconds before auto-connecting",
    )
    parser.add_argument(
        "--silent-errors",
        action="store_true",
        help="Log connection errors without showing popup dialogs",
    )
    return parser


def _load_server_config_if_autoconnect(app: SNMPControllerGUI, args: Any) -> dict[str, Any] | None:
    if not args.autoconnect:
        return None

    try:
        api_url = f"http://{app.host_var.get()}:{app.port_var.get()}"
        resp = requests.get(f"{api_url}/config", timeout=5)
        if resp.status_code != 200:
            return None
        saved = resp.json()
        app._log("Configuration loaded from server")
        app.connected = True
        app.status_var.set(f"Connected: {app.host_var.get()}:{app.port_var.get()}")
        return cast("dict[str, Any]", saved)
    except requests.exceptions.RequestException:
        app._log("Server not available, trying local config files")
        return None


def _load_local_gui_config() -> dict[str, Any] | None:
    cfg_path_yaml = GUI_CONFIG_YAML_FILE
    cfg_path_json = GUI_CONFIG_JSON_FILE

    if cfg_path_yaml.exists():
        with cfg_path_yaml.open(encoding="utf-8") as file_handle:
            return cast("dict[str, Any]", yaml.safe_load(file_handle) or {})

    if cfg_path_json.exists():
        with cfg_path_json.open(encoding="utf-8") as file_handle:
            return cast("dict[str, Any]", json.load(file_handle))

    return None


def _load_saved_gui_config(app: SNMPControllerGUI, args: Any) -> dict[str, Any] | None:
    saved = _load_server_config_if_autoconnect(app, args)
    if saved is not None:
        return saved
    return _load_local_gui_config()


def _apply_saved_gui_config(app: SNMPControllerGUI, args: Any, saved: dict[str, Any]) -> None:
    if args.host is None and "host" in saved:
        host_val = saved.get("host")
        app.host_var.set("" if host_val is None else str(host_val))
    if args.port is None and "port" in saved:
        port_val = saved.get("port")
        app.port_var.set("" if port_val is None else str(port_val))

    if (
        "selected_trap" in saved
        and saved["selected_trap"] != "No traps available"
        and hasattr(app, "trap_var")
    ):
        app.trap_var.set(saved["selected_trap"])
    if "trap_index" in saved and hasattr(app, "trap_index_var"):
        app.trap_index_var.set(saved["trap_index"])
    if "trap_overrides" in saved:
        app.current_trap_overrides = saved["trap_overrides"]


def _apply_cli_overrides(app: SNMPControllerGUI, args: Any) -> None:
    if args.host:
        app.host_var.set(args.host)
    if args.port:
        app.port_var.set(str(args.port))

    app.silent_errors = args.silent_errors

    if args.autoconnect:
        delay_ms = (args.connect_delay * 1000) + 200
        app.root.after(delay_ms, app._connect)


def main() -> None:
    """Main entry point for the GUI application."""
    parser = _build_main_parser()
    args = parser.parse_args()

    root = ctk.CTk()
    app = SNMPControllerGUI(root)

    try:
        saved = _load_saved_gui_config(app, args)
        if saved:
            _apply_saved_gui_config(app, args, saved)
    except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
        app._log(f"Error loading config: {e}")

    _apply_cli_overrides(app, args)
    root.mainloop()


if __name__ == "__main__":
    main()
