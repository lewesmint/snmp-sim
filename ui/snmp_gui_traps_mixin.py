"""Trap destination and receiver behaviors for the SNMP GUI controller."""

# ruff: noqa: PLR2004

from __future__ import annotations

from tkinter import messagebox, ttk
from typing import Any

import customtkinter as ctk
import requests

from snmp_traps.trap_receiver import TrapReceiver


class SNMPGuiTrapsMixin:
    """Provide trap destination and receiver UI actions."""

    root: Any
    api_url: str
    trap_destinations: list[tuple[str, int]]
    dest_tree: Any
    dest_host_var: Any
    dest_port_var: Any
    trap_var: Any
    current_trap_overrides: dict[str, Any]
    oid_rows: list[dict[str, Any]]
    receiver_port_var: Any
    receiver_status_var: Any
    start_receiver_btn: Any
    stop_receiver_btn: Any

    _log: Any
    _show_notification: Any

    def _trap_poll_key(self, trap: dict[str, Any]) -> str:
        """Build a stable key for de-duplicating trap updates in UI polling."""
        timestamp = str(trap.get("timestamp", ""))
        trap_oid = str(trap.get("trap_oid_str", "unknown"))
        source = str(trap.get("source", "unknown"))
        return f"{timestamp}|{trap_oid}|{source}"

    def _get_local_receiver(self) -> TrapReceiver | None:
        """Return UI-local trap receiver if initialized."""
        receiver = getattr(self, "_ui_trap_receiver", None)
        if isinstance(receiver, TrapReceiver):
            return receiver
        return None

    def _on_ui_trap_received(self, trap_data: dict[str, Any]) -> None:
        """Thread-safe callback for traps received by UI-local receiver."""
        self.root.after(0, lambda: self._handle_ui_trap_received(trap_data))

    def _handle_ui_trap_received(self, trap_data: dict[str, Any]) -> None:
        """Handle trap reception on the Tk main thread."""
        self._log(
            "Received trap "
            f"{trap_data.get('trap_oid_str', 'unknown')} "
            f"from {trap_data.get('source', 'unknown')}"
        )

    def _get_local_received_traps(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return traps from UI-local receiver (most recent first)."""
        receiver = self._get_local_receiver()
        if receiver is None:
            return []
        traps = receiver.get_received_traps(limit=limit)
        return [trap for trap in traps if isinstance(trap, dict)]

    def _cancel_trap_polling(self) -> None:
        """Cancel scheduled trap polling job if present."""
        poll_job = getattr(self, "_trap_poll_job", None)
        if poll_job is None:
            return
        self.root.after_cancel(poll_job)
        self._trap_poll_job = None

    def _schedule_trap_polling(self) -> None:
        """Schedule next trap poll while receiver is running."""
        return

    def _prime_trap_polling_baseline(self) -> None:
        """Initialize polling baseline to avoid replaying historical traps in UI."""
        traps = self._get_local_received_traps(limit=1)
        if traps:
            self._last_seen_trap_key = self._trap_poll_key(traps[0])

    def _poll_received_traps(self) -> None:
        """Poll backend for newly received traps and surface them in UI logs."""
        return

    def _load_trap_destinations(self) -> None:
        """Load trap destinations from app config via API."""
        try:
            response = requests.get(f"{self.api_url}/trap-destinations", timeout=5)
            if response.status_code == 200:
                data = response.json()
                destinations = data.get("destinations", [])
                self.trap_destinations = [(d["host"], d["port"]) for d in destinations]
                self._update_dest_display()
                self._log(f"Loaded {len(self.trap_destinations)} trap destination(s) from config")
            else:
                self._log(f"Failed to load trap destinations: {response.text}", "WARNING")
                self.trap_destinations = [("localhost", 162)]
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            self._log(f"Failed to load trap destinations: {error}", "WARNING")
            self.trap_destinations = [("localhost", 162)]

    def _update_dest_display(self) -> None:
        """Update the destination display in the Treeview."""
        for item in self.dest_tree.get_children():
            self.dest_tree.delete(item)

        for host, port in self.trap_destinations:
            self.dest_tree.insert("", "end", values=(str(host), str(port)))

    def _add_destination(self) -> None:
        """Add a new trap destination via API."""
        try:
            host = self.dest_host_var.get().strip()
            port = int(self.dest_port_var.get().strip())
            if not host:
                messagebox.showerror("Error", "Host cannot be empty")
                return
            if port < 1 or port > 65535:
                messagebox.showerror("Error", "Port must be between 1 and 65535")
                return

            response = requests.post(
                f"{self.api_url}/trap-destinations",
                json={"host": host, "port": port},
                timeout=5,
            )
            if response.status_code == 200:
                self._load_trap_destinations()
                self._log(f"Added trap destination: {host}:{port}")
            else:
                messagebox.showerror("Error", f"Failed to add destination: {response.text}")
        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except (AttributeError, LookupError, OSError, TypeError) as error:
            messagebox.showerror("Error", f"Failed to add destination: {error}")

    def _remove_destination(self) -> None:
        """Remove the selected destinations via API."""
        selected_items = self.dest_tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select destinations to remove.")
            return

        to_remove: list[tuple[str, int]] = []
        for item in selected_items:
            values = self.dest_tree.item(item, "values")
            if len(values) >= 2:
                host, port = values[0], values[1]
                try:
                    port_int = int(port)
                    to_remove.append((host, port_int))
                except ValueError:
                    self._log(f"Error converting port '{port}' to int", "WARNING")

        removed_hosts = []
        for host, port in to_remove:
            try:
                response = requests.request(
                    "DELETE",
                    f"{self.api_url}/trap-destinations",
                    json={"host": host, "port": port},
                    timeout=5,
                )
                if response.status_code == 200:
                    removed_hosts.append(f"{host}:{port}")
                else:
                    self._log(f"Failed to remove {host}:{port}: {response.text}", "WARNING")
            except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
                self._log(f"Failed to remove {host}:{port}: {error}", "ERROR")

        self._load_trap_destinations()

        if removed_hosts:
            self._log(f"Removed trap destinations: {', '.join(removed_hosts)}")
        else:
            self._log("No destinations were removed", "WARNING")

    def _update_forced_display(self) -> None:
        """Update the forced OIDs display (legacy method - kept for compatibility)."""
        return

    def _set_trap_override(self) -> None:
        """Set a trap-specific OID override (legacy method - kept for compatibility)."""
        messagebox.showinfo(
            "Use Table",
            "Please use the table above to set overrides and click 'Save Overrides'",
        )

    def _clear_trap_overrides(self) -> None:
        """Clear all overrides for the current trap."""
        trap_name = self.trap_var.get()
        if not trap_name or trap_name == "No traps available":
            messagebox.showwarning("No Trap Selected", "Please select a trap first.")
            return

        self.current_trap_overrides.clear()

        try:
            response = requests.delete(f"{self.api_url}/trap-overrides/{trap_name}", timeout=5)
            if response.status_code == 200:
                for row in self.oid_rows:
                    if row.get("is_index", False):
                        continue
                    row["use_override_var"].set(False)
                    row["override_entry"].delete(0, "end")
                self._log(f"Cleared all overrides for trap: {trap_name}")
            else:
                messagebox.showerror("Error", f"Failed to clear overrides: {response.text}")
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            messagebox.showerror("Error", f"Failed to clear overrides: {error}")

    def _start_trap_receiver(self) -> None:
        """Start the trap receiver."""
        try:
            port = int(self.receiver_port_var.get())
            receiver = self._get_local_receiver()
            if receiver and receiver.is_running():
                self.receiver_status_var.set(f"Receiver: Running on port {port}")
                self.start_receiver_btn.configure(state="disabled")
                self.stop_receiver_btn.configure(state="normal")
                self._log(f"Trap receiver already running on port {receiver.port}")
                return

            receiver = TrapReceiver(
                host="0.0.0.0",  # noqa: S104
                port=port,
                community="public",
                on_trap_callback=self._on_ui_trap_received,
            )
            receiver.start()
            self._ui_trap_receiver = receiver

            self.receiver_status_var.set(f"Receiver: Running on port {port}")
            self.start_receiver_btn.configure(state="disabled")
            self.stop_receiver_btn.configure(state="normal")
            self._log(f"Trap receiver started locally on 0.0.0.0:{port}")
            self._prime_trap_polling_baseline()

        except ValueError:
            messagebox.showerror("Error", "Invalid port number")
        except (AttributeError, LookupError, OSError, TypeError) as error:
            error_msg = f"Failed to start trap receiver: {error}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _stop_trap_receiver(self) -> None:
        """Stop the trap receiver."""
        try:
            receiver = self._get_local_receiver()
            if receiver and receiver.is_running():
                receiver.stop()

            self.receiver_status_var.set("Receiver: Stopped")
            self.start_receiver_btn.configure(state="normal")
            self.stop_receiver_btn.configure(state="disabled")
            self._cancel_trap_polling()
            self._log("Trap receiver stopped (local UI receiver)")

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as error:
            error_msg = f"Failed to stop trap receiver: {error}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _show_trap_notification(
        self,
        trap_name: str,
        trap_oid: str,
        timestamp: str,
        varbinds: list[dict[str, Any]],
    ) -> None:
        """Show a custom notification dialog with trap details and varbinds table."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Test Trap Received!")
        dialog.geometry("700x400")
        dialog.transient(self.root)
        dialog.grab_set()

        header_frame = ctk.CTkFrame(dialog)
        header_frame.pack(fill="x", padx=20, pady=20)

        title_label = ctk.CTkLabel(
            header_frame,
            text="✓ Successfully sent and received test trap!",
            font=("", 16, "bold"),
            text_color="green",
        )
        title_label.pack(pady=(0, 10))

        info_frame = ctk.CTkFrame(header_frame)
        info_frame.pack(fill="x")

        ctk.CTkLabel(info_frame, text=f"Trap: {trap_name}", font=("", 13)).pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"OID: {trap_oid}", font=("", 13)).pack(anchor="w", pady=2)
        ctk.CTkLabel(info_frame, text=f"Received at: {timestamp}", font=("", 13)).pack(
            anchor="w",
            pady=2,
        )

        varbinds_label = ctk.CTkLabel(dialog, text="Varbinds:", font=("", 14, "bold"))
        varbinds_label.pack(anchor="w", padx=20, pady=(10, 5))

        tree_frame = ctk.CTkFrame(dialog)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side="right", fill="y")

        varbinds_tree = ttk.Treeview(
            tree_frame,
            columns=("OID", "Value", "Type"),
            show="headings",
            yscrollcommand=tree_scroll.set,
            height=10,
        )
        varbinds_tree.pack(fill="both", expand=True)
        tree_scroll.config(command=varbinds_tree.yview)

        varbinds_tree.heading("OID", text="OID")
        varbinds_tree.heading("Value", text="Value")
        varbinds_tree.heading("Type", text="Type")

        varbinds_tree.column("OID", width=300)
        varbinds_tree.column("Value", width=300)
        varbinds_tree.column("Type", width=150)

        for vb in varbinds:
            vb_oid = vb.get("oid_str", "unknown")
            vb_value = vb.get("value", "")
            vb_type = vb.get("type", "")
            varbinds_tree.insert("", "end", values=(vb_oid, vb_value, vb_type))

        close_btn = ctk.CTkButton(dialog, text="Close", command=dialog.destroy, width=100)
        close_btn.pack(pady=(0, 20))

        dialog.update_idletasks()
        x_pos = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y_pos = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x_pos}+{y_pos}")
