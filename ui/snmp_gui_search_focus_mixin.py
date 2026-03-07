"""Search and focus/navigation mixin for SNMP GUI."""

# mypy: disable-error-code=attr-defined
# pyright: reportAttributeAccessIssue=false
# ruff: noqa: ANN401,D101,PLR0915,PLR2004,TRY300

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Any


class SNMPGuiSearchFocusMixin:
    _search_term: str
    _search_matches: list[tuple[str, str]]
    _search_current_index: int
    _search_setting_selection: bool
    _pending_oid_focus: dict[str, str | None] | None
    _pending_oid_focus_retries: int

    @staticmethod
    def _search_term_matches(search_term: str, oid: str, item_text: str) -> bool:
        lowered = search_term.lower()
        return (
            lowered in item_text.lower()
            or search_term in oid
            or lowered in oid.lower()
        )

    @staticmethod
    def _metadata_matches(search_term: str, oid_str: str, name: str, mib: str) -> bool:
        lowered = search_term.lower()
        return (
            lowered in name.lower()
            or lowered in mib.lower()
            or search_term in oid_str
            or lowered in oid_str.lower()
        )

    def _search_item_oid(self, item: str) -> tuple[str, bool]:
        item_values = self.oid_tree.item(item, "values")
        base_oid = item_values[0] if item_values else ""
        item_tags = self.oid_tree.item(item, "tags")
        is_entry = "table-entry" in item_tags
        oid = base_oid
        if is_entry and len(item_values) >= 2:
            table_oid = item_values[0]
            instance = item_values[1]
            if table_oid and instance:
                oid = f"{table_oid}.{instance}"
        return oid, is_entry

    def _append_metadata_matches(
        self,
        *,
        search_term: str,
        base_oid: str,
        matches: list[tuple[str, str]],
        seen_oids: set[str],
    ) -> None:
        for oid_str, metadata in self.oid_metadata.items():
            if oid_str in seen_oids or not oid_str.startswith(base_oid + "."):
                continue
            name = metadata.get("name", "")
            mib = metadata.get("mib", "")
            obj_type = metadata.get("type", "")
            display_name = name or oid_str

            if "SEQUENCE" in obj_type and "Entry" in name:
                continue

            if self._metadata_matches(search_term, oid_str, name, mib):
                matches.append((oid_str, display_name))
                seen_oids.add(oid_str)

    def _dfs_collect_matches(
        self,
        *,
        item: str,
        search_term: str,
        matches: list[tuple[str, str]],
        seen_oids: set[str],
    ) -> None:
        oid, is_entry = self._search_item_oid(item)
        item_text = self.oid_tree.item(item, "text")

        if oid and oid not in seen_oids and self._search_term_matches(search_term, oid, item_text):
            matches.append((oid, item_text))
            seen_oids.add(oid)

        for child_item in self.oid_tree.get_children(item):
            self._dfs_collect_matches(
                item=child_item,
                search_term=search_term,
                matches=matches,
                seen_oids=seen_oids,
            )

        if oid and not is_entry:
            self._append_metadata_matches(
                search_term=search_term,
                base_oid=oid,
                matches=matches,
                seen_oids=seen_oids,
            )

    def _collect_search_matches(self, search_term: str) -> list[tuple[str, str]]:
        matches: list[tuple[str, str]] = []
        seen_oids: set[str] = set()
        for root_item in self.oid_tree.get_children(""):
            self._dfs_collect_matches(
                item=root_item,
                search_term=search_term,
                matches=matches,
                seen_oids=seen_oids,
            )
        return matches

    def _advance_existing_search(self, search_term: str) -> bool:
        if search_term != self._search_term or not self._search_matches:
            return False
        self._search_current_index = (self._search_current_index + 1) % len(self._search_matches)
        self._show_search_match(self._search_current_index)
        return True

    def _on_search_first(self, _event: Any = None) -> None:
        """Start a new search or continue if search term changed."""
        search_term = self.search_var.get().strip()
        if not search_term:
            messagebox.showwarning("Search", "Please enter a search term")
            return

        if self._advance_existing_search(search_term):
            return

        matches = self._collect_search_matches(search_term)

        if not matches:
            messagebox.showinfo("Search", f"No matches found for '{search_term}'")
            self._search_matches.clear()
            self._search_term = ""
            return

        self._search_matches = matches
        self._search_current_index = 0
        self._search_term = search_term

        self._show_search_match(0)

        self._log(f"Found {len(matches)} match(es) for '{search_term}'")

    def _on_search_next(self) -> None:
        """Show the next search match."""
        if not self._search_matches:
            return

        self._search_current_index = (self._search_current_index + 1) % len(self._search_matches)
        self._show_search_match(self._search_current_index)

    def _show_search_match(self, index: int) -> None:
        """Display the search match at the given index. Loads missing hierarchy if needed."""
        if index >= len(self._search_matches):
            return

        oid_str, display_name = self._search_matches[index]
        match_num = index + 1
        total_matches = len(self._search_matches)

        if oid_str in self.oid_to_item:
            item_id = self.oid_to_item[oid_str]
            self._expand_path_to_item(item_id)
            self.oid_tree.see(item_id)
            self._search_setting_selection = True
            self.oid_tree.selection_set(item_id)
            self._ensure_oid_name_width(item_id)
            self._log(f"Match {match_num}/{total_matches}: {display_name} ({oid_str})")
            self.root.after(10, lambda: setattr(self, "_search_setting_selection", False))
            return

        oid_parts = oid_str.split(".")
        deepest_parent_oid = None
        for depth in range(len(oid_parts), 0, -1):
            parent_oid = ".".join(oid_parts[:depth])
            if parent_oid in self.oid_to_item:
                deepest_parent_oid = parent_oid
                break

        if deepest_parent_oid is None:
            self._log(
                f"Match {match_num}/{total_matches} (root not found): {display_name} ({oid_str})",
            )
            return

        parent_item = self.oid_to_item[deepest_parent_oid]
        parent_tags = self.oid_tree.item(parent_item, "tags")
        is_table_parent = "table" in parent_tags

        if is_table_parent:
            self._log(f"Loading table {deepest_parent_oid}...", "INFO")

        self.oid_tree.item(parent_item, open=True)
        self.oid_tree.update_idletasks()

        event_mock = type("Event", (), {"widget": self.oid_tree})()
        self._on_node_open(event_mock)

        max_retries = 20 if is_table_parent else 10
        base_wait = 200 if is_table_parent else 100
        long_wait = 500 if is_table_parent else 300

        def attempt_select(retry_count: int = 0) -> None:
            if oid_str in self.oid_to_item:
                item_id = self.oid_to_item[oid_str]
                try:
                    self.oid_tree.item(item_id)
                    self._expand_path_to_item(item_id)
                    self.oid_tree.see(item_id)
                    self._search_setting_selection = True
                    self.oid_tree.selection_set(item_id)
                    self._ensure_oid_name_width(item_id)
                    self._log(f"Match {match_num}/{total_matches}: {display_name} ({oid_str})")
                    self.root.after(10, lambda: setattr(self, "_search_setting_selection", False))
                    return
                except tk.TclError:
                    pass

            if is_table_parent and retry_count > 0 and retry_count % 5 == 0:
                self._log(f"Still loading table... ({retry_count}/{max_retries})", "DEBUG")

            if retry_count < max_retries:
                wait_time = base_wait if retry_count < 3 else long_wait
                self.root.after(wait_time, lambda: attempt_select(retry_count + 1))
            else:
                self._search_setting_selection = False
                self._log(
                    f"Match {match_num}/{total_matches} (could not load): "
                    f"{display_name} ({oid_str})",
                )

        self.root.after(base_wait, attempt_select)

    def _expand_path_to_oid(self, target_oid: tuple[int, ...]) -> None:
        """Expand the tree path to make the given OID visible."""
        if not self.oids_data:
            return

        path_oids = []
        for i in range(1, len(target_oid) + 1):
            partial_oid = target_oid[:i]
            oid_str = ".".join(str(x) for x in partial_oid)
            if oid_str in self.oid_to_item:
                path_oids.append(oid_str)

        for path_oid in path_oids:
            if path_oid in self.oid_to_item:
                item = self.oid_to_item[path_oid]
                self.oid_tree.item(item, open=True)
                self.oid_tree.update_idletasks()

    def _expand_path_to_item(self, item: str) -> None:
        """Expand all ancestors of the given item."""
        path = []
        current = item
        while current:
            path.append(current)
            current = self.oid_tree.parent(current)
        path.reverse()
        for node in path:
            self.oid_tree.item(node, open=True)
            if "table" in self.oid_tree.item(node, "tags"):
                children = self.oid_tree.get_children(node)
                if children and "placeholder" in self.oid_tree.item(children[0], "tags"):
                    oid_str = self.oid_tree.set(node, "oid")
                    if oid_str:
                        self.executor.submit(self._discover_table_instances, node, oid_str)

    def _on_tab_change(self) -> None:
        """Handle tab changes to restore OID tree focus when returning from Table View."""
        try:
            current_tab = self.tabview.get()
        except (AttributeError, LookupError, OSError, TypeError, ValueError):
            current_tab = None

        if current_tab == "OID Tree":
            self._apply_pending_oid_focus()

    def _set_pending_oid_focus(
        self,
        table_oid: str,
        instance: str | None,
        column_oid: str | None = None,
    ) -> None:
        """Store a pending focus request for the OID tree."""
        self._pending_oid_focus = {
            "table_oid": table_oid,
            "instance": instance,
            "column_oid": column_oid,
        }
        self._pending_oid_focus_retries = 0

    def _apply_pending_oid_focus(self) -> None:
        """Restore focus in the OID tree based on the last table selection/edit."""
        if not self._pending_oid_focus:
            return

        table_oid = self._pending_oid_focus.get("table_oid")
        instance = self._pending_oid_focus.get("instance")
        column_oid = self._pending_oid_focus.get("column_oid")

        if not table_oid:
            return

        table_item = self.oid_to_item.get(table_oid)
        if not table_item:
            return

        self._expand_path_to_item(table_item)
        self.oid_tree.item(table_item, open=True)

        target_item = table_item
        if instance:
            entry_item = self._find_table_entry_item(table_item, instance)
            if entry_item:
                target_item = entry_item
                if column_oid:
                    column_item = self._find_table_column_item(entry_item, column_oid, instance)
                    if column_item:
                        target_item = column_item
            elif self._pending_oid_focus_retries < 5:
                self._pending_oid_focus_retries += 1
                self.executor.submit(self._discover_table_instances, table_item, table_oid)
                self.root.after(200, self._apply_pending_oid_focus)
                return

        self.oid_tree.selection_set(target_item)
        self.oid_tree.focus(target_item)
        self.oid_tree.see(target_item)
        self._update_selected_info(target_item)
        self._ensure_oid_name_width(target_item)
        self._pending_oid_focus = None

    def _find_table_entry_item(self, table_item: str, instance: str) -> str | None:
        """Find a table-entry item under the table node for the given instance."""
        for child in self.oid_tree.get_children(table_item):
            if "table-entry" in self.oid_tree.item(child, "tags"):
                child_instance = self.oid_tree.set(child, "instance")
                if child_instance == instance:
                    return str(child)
        return None

    def _find_table_column_item(
        self,
        entry_item: str,
        column_oid: str,
        instance: str,
    ) -> str | None:
        """Find a table-column item under an entry for a given column OID and instance."""
        for child in self.oid_tree.get_children(entry_item):
            if "table-column" in self.oid_tree.item(child, "tags"):
                child_oid = self.oid_tree.set(child, "oid")
                child_instance = self.oid_tree.set(child, "instance")
                if child_oid == column_oid and child_instance == instance:
                    return str(child)
        return None
