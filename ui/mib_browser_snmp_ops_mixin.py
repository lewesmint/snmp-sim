"""SNMP operation mixin for the standalone MIB Browser window."""

# pylint: disable=attribute-defined-outside-init

from __future__ import annotations

import asyncio
import tkinter as tk
from datetime import UTC, datetime
from tkinter import messagebox, ttk
from typing import Any

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData,
    ContextData,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
    next_cmd,
    set_cmd,
    walk_cmd,
)
from pysnmp.proto.error import StatusInformation
from pysnmp.proto.rfc1902 import OctetString

from ui.common import format_snmp_value


class MIBBrowserSnmpOpsMixin:
    """Mixin for SNMP operations and result-tree helpers."""

    results_tree: ttk.Treeview
    oid_var: tk.StringVar
    value_var: tk.StringVar
    status_var: tk.StringVar
    window: Any
    logger: Any
    agent_tree_items: dict[str, str]
    agent_results: dict[str, dict[str, Any]]

    def _create_object_identity(self, oid_input: str) -> tuple[Any, str]:
        raise NotImplementedError

    def _get_connection_params(self) -> tuple[str, int, str]:
        raise NotImplementedError

    def _format_mib_error(self, error: Exception) -> str:
        raise NotImplementedError

    def _get_icon_for_oid(self, oid_str: str) -> tk.PhotoImage | None:
        raise NotImplementedError

    def _get_oid_metadata_from_mib(self, oid_str: str) -> dict[str, Any]:
        raise NotImplementedError

    def _on_node_open(self, event: tk.Event[tk.Misc]) -> None:
        """Handle node open events (for future lazy loading if needed)."""
        _ = event

    def _expand_all(self) -> None:
        """Expand all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.results_tree.item(item, open=True)
            for c in self.results_tree.get_children(item):
                _recurse(c)

        for root in self.results_tree.get_children(""):
            _recurse(root)

    def _collapse_all(self) -> None:
        """Collapse all nodes in the tree."""

        def _recurse(item: str) -> None:
            self.results_tree.item(item, open=False)
            for c in self.results_tree.get_children(item):
                _recurse(c)

        for root in self.results_tree.get_children(""):
            _recurse(root)

    def _get_or_create_agent_node(self, host: str, port: int) -> str:
        """Get or create the tree node for an agent."""
        agent_key = f"{host}:{port}"

        if agent_key not in self.agent_tree_items:
            agent_label = f"🖥️ {agent_key}"
            item = self.results_tree.insert("", "end", text=agent_label, values=("", "", ""))
            self.results_tree.item(item, open=True)
            self.agent_tree_items[agent_key] = item
            self.agent_results[agent_key] = {"operations": {}, "last_updated": ""}

        return self.agent_tree_items[agent_key]

    def _get_or_create_operation_node(self, agent_item: str, operation: str, oid: str) -> str:
        """Get or create the tree node for an operation under an agent."""
        agent_key = None
        for key, item in self.agent_tree_items.items():
            if item == agent_item:
                agent_key = key
                break

        if not agent_key:
            return ""

        op_key = f"{operation}:{oid}"
        op_children = self.results_tree.get_children(agent_item)

        for child in op_children:
            if self.results_tree.item(child, "text").startswith(f"→ {operation}"):
                if op_key not in self.agent_results[agent_key]["operations"]:
                    self.agent_results[agent_key]["operations"][op_key] = {"results": []}
                return child

        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        op_label = f"→ {operation} {oid} [{timestamp}]"
        op_item = self.results_tree.insert(agent_item, "end", text=op_label, values=("", "", ""))
        self.results_tree.item(op_item, open=True)
        self.agent_results[agent_key]["operations"][op_key] = {"results": []}
        self.agent_results[agent_key]["last_updated"] = timestamp

        return op_item

    def _snmp_get(self) -> None:
        """Execute SNMP GET command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GET on {display_oid}...")
        self.logger.log(f"MIB Browser: GET {display_oid} from {host}:{port}")

        try:

            async def async_get() -> tuple[Any, ...]:
                try:
                    return await get_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                except StatusInformation as e:
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, var_binds = asyncio.run(async_get())
            _ = error_index

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser GET error: {error_indication}", "ERROR")
                messagebox.showerror("SNMP GET Error", str(error_indication), parent=self.window)
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser GET error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP GET Error",
                    error_status.prettyPrint(),
                    parent=self.window,
                )
                return

            agent_item = self._get_or_create_agent_node(host, port)
            op_item = self._get_or_create_operation_node(agent_item, "GET", display_oid)

            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = format_snmp_value(var_bind[1])
                type_str = type(var_bind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                icon = self._get_icon_for_oid(oid_str)

                self.results_tree.insert(
                    op_item,
                    "end",
                    text=name,
                    image=icon or "",
                    values=(oid_str, type_str, value),
                )

            self.status_var.set(f"GET completed: {len(var_binds)} result(s)")
            self.logger.log(f"MIB Browser: GET {display_oid} returned {len(var_binds)} result(s)")

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser GET error: {e}", "ERROR")
            messagebox.showerror("SNMP GET Error", error_msg, parent=self.window)

    def _snmp_getnext(self) -> None:
        """Execute SNMP GETNEXT command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing GETNEXT on {display_oid}...")
        self.logger.log(f"MIB Browser: GETNEXT {display_oid} from {host}:{port}")

        try:

            async def async_next() -> tuple[Any, ...]:
                target = await UdpTransportTarget.create((host, port))

                try:
                    return await next_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                except StatusInformation as e:
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, var_binds = asyncio.run(async_next())
            _ = error_index

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser GETNEXT error: {error_indication}", "ERROR")
                messagebox.showerror(
                    "SNMP GETNEXT Error",
                    str(error_indication),
                    parent=self.window,
                )
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser GETNEXT error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP GETNEXT Error",
                    error_status.prettyPrint(),
                    parent=self.window,
                )
                return

            agent_item = self._get_or_create_agent_node(host, port)
            op_item = self._get_or_create_operation_node(agent_item, "GETNEXT", display_oid)

            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = format_snmp_value(var_bind[1])
                type_str = type(var_bind[1]).__name__
                name = self._get_name_from_oid(oid_str)
                icon = self._get_icon_for_oid(oid_str)

                self.results_tree.insert(
                    op_item,
                    "end",
                    text=name,
                    image=icon or "",
                    values=(oid_str, type_str, value),
                )

            if var_binds:
                next_oid = str(var_binds[0][0])
                self.oid_var.set(next_oid)
                self.logger.log(f"Updated OID field to {next_oid} for next iteration", "DEBUG")

            self.status_var.set(f"GETNEXT completed: {len(var_binds)} result(s)")
            self.logger.log(
                f"MIB Browser: GETNEXT {display_oid} returned {len(var_binds)} result(s)",
            )

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser GETNEXT error: {e}", "ERROR")
            messagebox.showerror("SNMP GETNEXT Error", error_msg, parent=self.window)

    def _snmp_walk(self) -> None:
        """Execute SNMP WALK command."""
        oid = self.oid_var.get().strip()
        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return

        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing WALK on {display_oid}...")
        self.logger.log(f"MIB Browser: WALK {display_oid} from {host}:{port}")

        try:

            async def async_walk() -> list[tuple[Any, ...]]:
                walk_results = []
                target = await UdpTransportTarget.create((host, port))

                try:
                    iterator = walk_cmd(
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        target,
                        ContextData(),
                        ObjectType(obj_identity),
                    )
                    async for (
                        error_indication,
                        error_status,
                        error_index,
                        var_binds,
                    ) in iterator:
                        walk_results.append(
                            (error_indication, error_status, error_index, var_binds),
                        )
                except StatusInformation as e:
                    error_indication = e.get("errorIndication", str(e))
                    walk_results.append((error_indication, None, None, []))

                return walk_results

            walk_results = asyncio.run(async_walk())

            agent_item = self._get_or_create_agent_node(host, port)
            op_item = self._get_or_create_operation_node(agent_item, "WALK", display_oid)

            result_count = 0
            for error_indication, error_status, error_index, var_binds in walk_results:
                _ = error_index
                if error_indication:
                    self.status_var.set(f"Error: {error_indication}")
                    self.logger.log(f"MIB Browser WALK error: {error_indication}", "ERROR")
                    messagebox.showerror(
                        "SNMP WALK Error",
                        str(error_indication),
                        parent=self.window,
                    )
                    return
                if error_status:
                    self.status_var.set(f"Error: {error_status}")
                    self.logger.log(f"MIB Browser WALK error: {error_status}", "ERROR")
                    messagebox.showerror("SNMP WALK Error", str(error_status), parent=self.window)
                    return

                for var_bind in var_binds:
                    oid_str = str(var_bind[0])
                    value = format_snmp_value(var_bind[1])
                    type_str = type(var_bind[1]).__name__
                    name = self._get_name_from_oid(oid_str)
                    icon = self._get_icon_for_oid(oid_str)

                    self.results_tree.insert(
                        op_item,
                        "end",
                        text=name,
                        image=icon or "",
                        values=(oid_str, type_str, value),
                    )
                    result_count += 1

            self.status_var.set(f"WALK completed: {result_count} result(s)")
            self.logger.log(f"MIB Browser: WALK {display_oid} returned {result_count} result(s)")

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser WALK error: {e}", "ERROR")
            messagebox.showerror("SNMP WALK Error", error_msg, parent=self.window)

    def _snmp_set(self) -> None:
        """Execute SNMP SET command."""
        oid = self.oid_var.get().strip()
        value = self.value_var.get().strip()

        if not oid:
            messagebox.showwarning("No OID", "Please enter an OID", parent=self.window)
            return
        if not value:
            messagebox.showwarning("No Value", "Please enter a value to set", parent=self.window)
            return

        try:
            obj_identity, display_oid = self._create_object_identity(oid)
        except ValueError as e:
            messagebox.showerror("Invalid OID", str(e), parent=self.window)
            self.status_var.set(f"Error: {e}")
            return

        host, port, community = self._get_connection_params()
        self.status_var.set(f"Executing SET on {display_oid}...")
        self.logger.log(f"MIB Browser: SET {display_oid} = {value} on {host}:{port}")

        try:

            async def async_set() -> tuple[Any, ...]:
                try:
                    return await set_cmd(  # type: ignore[no-any-return]
                        SnmpEngine(),
                        CommunityData(community, mpModel=1),
                        await UdpTransportTarget.create((host, port)),
                        ContextData(),
                        ObjectType(obj_identity, OctetString(value)),
                    )
                except StatusInformation as e:
                    error_indication = e.get("errorIndication", str(e))
                    return (error_indication, None, None, [])

            error_indication, error_status, error_index, _var_binds = asyncio.run(async_set())
            _ = error_index

            if error_indication:
                self.status_var.set(f"Error: {error_indication}")
                self.logger.log(f"MIB Browser SET error: {error_indication}", "ERROR")
                messagebox.showerror("SNMP SET Error", str(error_indication), parent=self.window)
                return
            if error_status:
                self.status_var.set(f"Error: {error_status.prettyPrint()}")
                self.logger.log(f"MIB Browser SET error: {error_status.prettyPrint()}", "ERROR")
                messagebox.showerror(
                    "SNMP SET Error",
                    error_status.prettyPrint(),
                    parent=self.window,
                )
                return

            agent_item = self._get_or_create_agent_node(host, port)
            op_item = self._get_or_create_operation_node(agent_item, "SET", display_oid)

            result_text = f"SET {display_oid} = {value}"
            icon = self._get_icon_for_oid(display_oid)
            self.results_tree.insert(
                op_item,
                "end",
                text=result_text,
                image=icon or "",
                values=(display_oid, "OctetString", value),
            )

            self.status_var.set("SET completed successfully")
            self.logger.log(f"MIB Browser: SET {display_oid} = {value} successful")

        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = self._format_mib_error(e)
            self.status_var.set(f"Error: {error_msg.split(chr(10), maxsplit=1)[0]}")
            self.logger.log(f"MIB Browser SET error: {e}", "ERROR")
            messagebox.showerror("SNMP SET Error", error_msg, parent=self.window)

    def _get_name_from_oid(self, oid_str: str) -> str:
        """Get human-readable name from OID using loaded MIBs."""
        metadata = self._get_oid_metadata_from_mib(oid_str)
        if metadata.get("name"):
            return str(metadata["name"])

        parts = oid_str.split(".")
        for i in range(len(parts), 0, -1):
            base_oid = ".".join(parts[:i])
            base_metadata = self._get_oid_metadata_from_mib(base_oid)
            if base_metadata.get("name"):
                instance = ".".join(parts[i:])
                return f"{base_metadata['name']}.{instance}" if instance else base_metadata["name"]

        return oid_str

    def _build_hierarchical_tree(self, results: list[tuple[str, str, str]]) -> None:
        """Build a hierarchical tree from WALK results."""
        oid_to_item: dict[str, str] = {}

        for oid_str, type_str, value in results:
            parts = oid_str.split(".")
            parent_oid = ".".join(parts[:-1]) if len(parts) > 1 else ""

            parent_item = ""
            if parent_oid and parent_oid in oid_to_item:
                parent_item = oid_to_item[parent_oid]

            name = self._get_name_from_oid(oid_str)

            item = self.results_tree.insert(
                parent_item,
                "end",
                text=name,
                values=(oid_str, type_str, value),
            )

            oid_to_item[oid_str] = item

        for item in self.results_tree.get_children():
            self.results_tree.item(item, open=True)
