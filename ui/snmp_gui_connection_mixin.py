"""Connection and trap sending mixin for SNMP GUI."""

# pyright: reportAttributeAccessIssue=false, reportGeneralTypeIssues=false
# ruff: noqa: ANN401,D101,D102,SLF001

from __future__ import annotations

import contextlib
import time
import traceback
from datetime import UTC, datetime
from tkinter import messagebox
from typing import Any, cast

import requests
import yaml

from app.model_paths import CONFIG_DIR, GUI_CONFIG_YAML_FILE
from ui.common import save_gui_log


class SNMPGuiConnectionMixin:
    connected: bool
    api_url: str
    silent_errors: bool
    mib_browser: Any
    oids_data: dict[str, tuple[int, ...]]
    oid_metadata: dict[str, dict[str, Any]]
    oid_values: dict[str, Any]
    table_instances_data: dict[str, Any]
    trap_destinations: list[tuple[str, int]]
    current_trap_overrides: dict[str, Any]
    oid_rows: list[dict[str, Any]]
    mibs_data: dict[str, Any]
    current_mermaid_diagram: str
    tabview: Any
    connect_button: Any
    status_var: Any
    mibs_text: Any
    logger: Any
    root: Any
    log_text: Any
    host_var: Any
    port_var: Any
    trap_var: Any
    trap_index_var: Any
    receiver_port_var: Any

    def enable_oid_tree_tab(self) -> None:
        pass

    def enable_traps_tab(self) -> None:
        pass

    def enable_links_tab(self) -> None:
        pass

    def _populate_oid_tree(self) -> None:
        pass

    def _load_traps(self) -> None:
        pass

    def _stop_trap_receiver(self) -> None:
        pass

    def _resolve_table_oid(self, oid_str: str, _row: dict[str, Any] | None = None) -> str | None:
        resolver = getattr(super(), "_resolve_table_oid", None)
        if callable(resolver):
            try:
                return cast("str | None", resolver(oid_str, _row))  # pylint: disable=not-callable
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                return None
        return None

    def _get_local_received_traps(self, limit: int | None = None) -> list[dict[str, Any]]:
        del limit
        return []

    def _show_trap_notification(
        self,
        trap_name: str,
        trap_oid: str,
        timestamp: str,
        varbinds: list[dict[str, Any]],
    ) -> None:
        pass

    def _toggle_connection(self) -> None:
        """Connect or disconnect from the REST API."""
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _fetch_mibs_with_fallback(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.api_url}/mibs-with-dependencies", timeout=5)
            response.raise_for_status()
            return cast("dict[str, Any]", response.json())
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            response = requests.get(f"{self.api_url}/mibs", timeout=5)
            response.raise_for_status()
            mibs_data = response.json()
            configured_mibs = mibs_data.get("mibs", [])
            return {
                "configured_mibs": configured_mibs,
                "tree": {
                    mib: {
                        "direct_deps": [],
                        "transitive_deps": [],
                        "is_configured": True,
                    }
                    for mib in configured_mibs
                },
            }

    def _fetch_oids_data(self) -> dict[str, tuple[int, ...]]:
        response = requests.get(f"{self.api_url}/oids", timeout=5)
        response.raise_for_status()
        oids_data = response.json()
        oids = oids_data.get("oids", {})
        try:
            return {str(k): tuple(v) for k, v in oids.items()}
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            return {}

    def _fetch_oid_metadata_with_fallback(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.api_url}/oid-metadata", timeout=5)
            response.raise_for_status()
            metadata_data = response.json()
            return cast("dict[str, Any]", metadata_data.get("metadata", {}))
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Failed to fetch OID metadata: {e}", "WARNING")
            return {}

    def _fetch_bulk_values_with_fallback(self) -> dict[str, Any]:
        self._log("Loading all OID values in bulk...")
        try:
            response = requests.get(f"{self.api_url}/values/bulk", timeout=30)
            response.raise_for_status()
            values_data = response.json()
            values = values_data.get("values", {})
            self._log(f"Loaded {len(values)} OID values")
            return cast("dict[str, Any]", values)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Failed to fetch bulk values: {e}", "WARNING")
            return {}

    def _fetch_table_instances_bulk_with_fallback(self) -> dict[str, Any]:
        self._log("Loading all table instances in bulk...")
        try:
            response = requests.get(f"{self.api_url}/tree/bulk", timeout=30)
            response.raise_for_status()
            tree_data = response.json()
            table_instances_data = tree_data.get("tables", {})
            total_instances = sum(
                len(t.get("instances", [])) for t in table_instances_data.values()
            )
            self._log(
                f"Loaded {len(table_instances_data)} tables with "
                f"{total_instances} total instances",
            )
            if table_instances_data:
                self._log(
                    f"Table OIDs loaded: {list(table_instances_data.keys())[:5]}...",
                    "DEBUG",
                )
            return cast("dict[str, Any]", table_instances_data)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Failed to fetch tree bulk data: {e}", "WARNING")
            traceback.print_exc()
            return {}

    def _finalize_successful_connection(
        self,
        configured_mibs_list: list[Any],
        oids_count: int,
    ) -> None:
        self.enable_oid_tree_tab()
        self.enable_traps_tab()
        self.enable_links_tab()

        if self.mib_browser:
            self.mib_browser.set_oid_metadata(self.oid_metadata)

        self._populate_oid_tree()

        self.connected = True
        self.connect_button.configure(text="Disconnect")
        self.status_var.set("Connected")
        self._log(
            f"Connected successfully. Found {len(configured_mibs_list)} MIBs "
            f"and {oids_count} OIDs",
        )
        self._load_traps()

    def _connect(self) -> None:
        """Connect to the REST API."""
        host = self.host_var.get().strip()
        port = self.port_var.get().strip()
        self.api_url = f"http://{host}:{port}"

        try:
            self.status_var.set("Connecting...")
            self._log(f"Connecting to {self.api_url}")

            mibs_dep_data = self._fetch_mibs_with_fallback()

            self._populate_mibs_tree(mibs_dep_data)
            configured_mibs_list = mibs_dep_data.get("configured_mibs", [])
            self.oids_data = self._fetch_oids_data()
            self.oid_metadata = self._fetch_oid_metadata_with_fallback()
            self.oid_values = self._fetch_bulk_values_with_fallback()
            self.table_instances_data = self._fetch_table_instances_bulk_with_fallback()

            self._finalize_successful_connection(
                configured_mibs_list=cast("list[Any]", configured_mibs_list),
                oids_count=len(self.oids_data),
            )

        except requests.exceptions.ConnectionError:
            error_msg = "Cannot connect to REST API. Is the agent running?"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            if not self.silent_errors:
                messagebox.showerror("Connection Error", error_msg)

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Error connecting: {e!s}"
            self._log(error_msg, "ERROR")
            self.status_var.set("Connection failed")
            if not self.silent_errors:
                messagebox.showerror("Error", error_msg)

    def _disconnect(self) -> None:
        """Disconnect from the REST API."""
        self.connected = False
        self.connect_button.configure(text="Connect")
        self.status_var.set("Disconnected")

        self.mibs_text.configure(state="normal")
        self.mibs_text.delete("1.0", "end")
        self.mibs_text.configure(state="disabled")
        self.mibs_data.clear()
        self.current_mermaid_diagram = ""

        if "OID Tree" in self.tabview._tab_dict:
            self.tabview.delete("OID Tree")
        if "Traps" in self.tabview._tab_dict:
            self.tabview.delete("Traps")

        self._log("Disconnected")

    def _populate_mibs_tree(self, mibs_dep_data: dict[str, Any]) -> None:
        """Populate the MIBs display with dependency information."""
        try:
            self.mibs_data.clear()

            tree = mibs_dep_data.get("tree", {})
            configured_mibs = mibs_dep_data.get("configured_mibs", [])
            transitive_deps = mibs_dep_data.get("transitive_dependencies", [])
            summary = mibs_dep_data.get("summary", {})

            display_text = "MIB DEPENDENCY SUMMARY\n"
            display_text += "=" * 60 + "\n\n"
            display_text += f"Configured MIBs ({summary.get('configured_count', 0)}):\n"
            if configured_mibs:
                display_text += f"  {', '.join(configured_mibs)}\n"
            else:
                display_text += "  (none)\n"

            display_text += f"\nTransitive Dependencies ({summary.get('transitive_count', 0)}):\n"
            if transitive_deps:
                display_text += f"  {', '.join(transitive_deps)}\n"
            else:
                display_text += "  (none)\n"

            display_text += f"\nTotal Unique MIBs: {summary.get('total_count', 0)}\n"
            display_text += "=" * 60 + "\n\n"
            display_text += "DETAILED DEPENDENCIES\n"
            display_text += "=" * 60 + "\n"

            for mib_name in configured_mibs:
                if mib_name not in tree:
                    continue
                mib_info = tree[mib_name]
                direct_deps = mib_info.get("direct_deps", [])
                transitive = mib_info.get("transitive_deps", [])

                display_text += f"\n{mib_name} (configured)\n"
                display_text += (
                    f"  Direct imports: {', '.join(direct_deps) if direct_deps else '(none)'}\n"
                )
                if transitive:
                    display_text += f"  Transitive: {', '.join(transitive)}\n"
                self.mibs_data[mib_name] = mib_info

            self.mibs_text.configure(state="normal")
            self.mibs_text.delete("1.0", "end")
            self.mibs_text.insert("1.0", display_text)
            self.mibs_text.configure(state="disabled")

            self._log(
                f"Populated MIB dependency display with {summary.get('total_count', 0)} total MIBs",
            )

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error populating MIB display: {e}", "ERROR")

    def _log(self, message: str, level: str = "INFO") -> None:
        """Add a message to the log window using the logger."""
        self.logger.log(message, level)

    def _on_close(self) -> None:
        """Save GUI log and configuration then quit."""
        try:
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                self._stop_trap_receiver()

            save_gui_log(self.log_text)

            cfg = {
                "host": self.host_var.get(),
                "port": self.port_var.get(),
                "trap_destinations": self.trap_destinations,
                "selected_trap": self.trap_var.get(),
                "trap_index": self.trap_index_var.get(),
                "trap_overrides": self.current_trap_overrides,
            }
            try:
                resp = requests.post(f"{self.api_url}/config", json=cfg, timeout=5)
                resp.raise_for_status()
                self._log("Configuration saved to server")
            except requests.exceptions.RequestException as e:
                self._log(f"Failed to save config to server: {e}", "ERROR")
                self._save_config_locally(cfg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Error during shutdown: {e}", "ERROR")

        try:
            self.root.destroy()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            with contextlib.suppress(AttributeError, LookupError, OSError, TypeError, ValueError):
                self.root.quit()

    def _save_config_locally(self, cfg: dict[str, Any]) -> None:
        """Fallback method to save config locally if server save fails."""
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with GUI_CONFIG_YAML_FILE.open("w", encoding="utf-8") as file_handle:
                yaml.safe_dump(cfg, file_handle)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            self._log(f"Failed to save config locally: {e}", "ERROR")

    def _collect_trap_overrides(self) -> dict[str, str]:
        """Collect override values from the UI table."""
        trap_overrides: dict[str, str] = {}

        for row in self.oid_rows:
            if row.get("is_sysuptime", False) or row.get("is_index", False):
                continue

            if row["use_override_var"].get():
                oid_name = row["oid_name"]
                override_value = row["override_entry"].get().strip()
                if override_value:
                    trap_overrides[oid_name] = override_value

        return trap_overrides

    def _resolve_oid_str_to_actual_oid(self, oid_str: str) -> Any | None:
        """Resolve a UI OID label like 'IF-MIB::ifOperStatus[2]' to an actual OID instance."""
        if "::" in oid_str and "[" in oid_str and "]" in oid_str:
            return self._resolve_table_oid(oid_str)

        for oid, metadata in self.oid_metadata.items():
            if oid_str in oid or oid_str in metadata.get("name", ""):
                return oid

        return None

    def _apply_trap_overrides(self, trap_overrides: dict[str, str]) -> int:
        """Apply trap override values by POSTing to /value. Returns count of successful updates."""
        applied = 0

        for oid_str, value in trap_overrides.items():
            try:
                actual_oid = self._resolve_oid_str_to_actual_oid(oid_str)
                if not actual_oid:
                    self._log(f"Could not resolve OID: {oid_str}", "WARNING")
                    continue

                update_payload = {"oid": actual_oid, "value": value}
                response = requests.post(f"{self.api_url}/value", json=update_payload, timeout=5)

                if response.ok:
                    applied += 1
                    self._log(f"Set OID {oid_str} = {value}")
                else:
                    self._log(f"Failed to set OID {oid_str}: {response.text}", "WARNING")

            except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
                self._log(f"Error setting OID {oid_str}: {exc}", "WARNING")

        return applied

    def _build_send_trap_payload(
        self,
        trap_name: str,
        dest_host: str,
        dest_port: int,
        community: str = "public",
        trap_type: str = "trap",
    ) -> dict[str, Any]:
        return {
            "trap_name": trap_name,
            "trap_type": trap_type,
            "dest_host": dest_host,
            "dest_port": dest_port,
            "community": community,
        }

    def _post_send_trap(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(f"{self.api_url}/send-trap", json=payload, timeout=5)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def _log_send_result(
        self,
        dest_host: str,
        dest_port: int,
        trap_name: str,
        result: dict[str, Any],
    ) -> None:
        timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
        trap_oid = result.get("trap_oid", "")
        oid_str = (
            ".".join(str(x) for x in trap_oid)
            if isinstance(trap_oid, (list, tuple))
            else str(trap_oid)
        )

        log_msg = f"[{timestamp}] Sent to {dest_host}:{dest_port}: {trap_name} (OID: {oid_str})"
        self.log_text.insert("end", "\n" + log_msg + "\n")
        self.log_text.see("end")

    def _log_send_failure(
        self,
        dest_host: str,
        dest_port: int,
        trap_name: str,
        error: Exception,
    ) -> None:
        timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] Failed to {dest_host}:{dest_port}: {trap_name} - {error}"
        self.log_text.insert("end", "\n" + log_msg + "\n")
        self.log_text.see("end")

    def _send_test_trap(self) -> None:
        """Send the selected trap to localhost on the receiver port."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap to send.")
            return

        try:
            port = int(self.receiver_port_var.get())

            trap_overrides = self._collect_trap_overrides()
            self._apply_trap_overrides(trap_overrides)

            payload = self._build_send_trap_payload(
                trap_name=trap_name,
                dest_host="localhost",
                dest_port=port,
                community="public",
                trap_type="trap",
            )

            result = self._post_send_trap(payload)

            timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S")
            trap_oid = result.get("trap_oid", "")
            oid_str = (
                ".".join(str(x) for x in trap_oid)
                if isinstance(trap_oid, (list, tuple))
                else str(trap_oid)
            )

            log_msg = (
                f"[{timestamp}] Sent test trap to localhost:{port}: {trap_name} (OID: {oid_str})"
            )
            self.log_text.insert("end", "\n" + log_msg + "\n")
            self.log_text.see("end")

            self._log(f"Test trap sent to localhost:{port}")

            time.sleep(0.5)

            try:
                traps = self._get_local_received_traps(limit=1)
                if traps:
                    received_trap = traps[0]
                    recv_timestamp = received_trap.get("timestamp", "")
                    recv_oid = received_trap.get("trap_oid_str", "unknown")
                    varbinds = received_trap.get("varbinds", [])

                    recv_log_msg = (
                        f"[{recv_timestamp}] Received trap: {trap_name} (OID: {recv_oid})"
                    )
                    self.log_text.insert("end", "\n" + recv_log_msg + "\n")

                    for vb in varbinds:
                        vb_oid = vb.get("oid_str", "unknown")
                        vb_value = vb.get("value", "")
                        self.log_text.insert("end", f"  - {vb_oid} = {vb_value}\n")

                    self.log_text.see("end")
                    self._show_trap_notification(trap_name, recv_oid, recv_timestamp, varbinds)
                else:
                    messagebox.showwarning(
                        "Trap Sent",
                        f"Test trap '{trap_name}' was sent to localhost:{port}\n\n"
                        "But no trap was received. Make sure the local UI receiver is running.",
                    )
            except (AttributeError, LookupError, OSError, TypeError, ValueError):
                messagebox.showinfo(
                    "Trap Sent",
                    f"Test trap '{trap_name}' sent to localhost:{port}",
                )

        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except (AttributeError, LookupError, OSError, TypeError) as exc:
            error_msg = f"Failed to send test trap: {exc}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _send_trap(self) -> None:
        """Send the selected trap to all configured destinations."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap to send.")
            return

        if not self.trap_destinations:
            messagebox.showerror("No Destinations", "Please add at least one trap destination.")
            return

        try:
            trap_overrides = self._collect_trap_overrides()
            applied = self._apply_trap_overrides(trap_overrides)

            if applied:
                self._log(f"Applied {applied} trap-specific OID override(s)")

            success_count = 0

            for dest_host, dest_port in self.trap_destinations:
                payload = self._build_send_trap_payload(
                    trap_name=trap_name,
                    dest_host=dest_host,
                    dest_port=dest_port,
                    community="public",
                    trap_type="trap",
                )

                try:
                    result = self._post_send_trap(payload)
                    self._log_send_result(dest_host, dest_port, trap_name, result)
                    success_count += 1
                except requests.exceptions.RequestException as exc:
                    self._log(
                        f"Failed to send trap to {dest_host}:{dest_port}: {exc}",
                        "ERROR",
                    )
                    self._log_send_failure(dest_host, dest_port, trap_name, exc)

            if success_count > 0:
                self._log(
                    f"Successfully sent trap '{trap_name}' to "
                    f"{success_count}/{len(self.trap_destinations)} destination(s)",
                )
                messagebox.showinfo(
                    "Success",
                    f"Trap '{trap_name}' sent to {success_count} destination(s)!",
                )
            else:
                messagebox.showerror("Error", "Failed to send trap to any destination")

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as exc:
            error_msg = f"Unexpected error sending trap: {exc}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
