#!/usr/bin/env python3
"""
Debug version to see exactly what events fire and when.
"""

import tkinter as tk
from tkinter import ttk
import time


class DebugDropdownTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Debug Dropdown Test")
        self.root.geometry("700x500")

        # Event log
        self.log_text = tk.Text(self.root, height=10, font=("Courier", 10))
        self.log_text.pack(fill="x", padx=10, pady=5)

        # Clear log button
        clear_btn = tk.Button(
            self.root,
            text="Clear Log",
            command=lambda: self.log_text.delete(1.0, tk.END),
        )
        clear_btn.pack(pady=2)

        # Create treeview
        self.tree = ttk.Treeview(
            self.root, columns=("col1", "col2", "col3"), show="headings"
        )
        self.tree.heading("col1", text="Column 1")
        self.tree.heading("col2", text="Column 2 (Enum)")
        self.tree.heading("col3", text="Column 3")

        self.tree.column("col1", width=150)
        self.tree.column("col2", width=200)
        self.tree.column("col3", width=150)

        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        # Add sample rows
        self.tree.insert("", "end", values=("Row 1", "1 (up)", "Value A"))
        self.tree.insert("", "end", values=("Row 2", "2 (down)", "Value B"))
        self.tree.insert("", "end", values=("Row 3", "1 (up)", "Value C"))

        # Create edit overlay
        self.edit_frame = tk.Frame(self.root, bg="white", relief="solid", borderwidth=1)
        self.edit_combo = ttk.Combobox(self.edit_frame, font=("Helvetica", 12))
        self.edit_combo.pack(padx=2, pady=2, fill="both", expand=True)

        # State
        self.editing_item = None
        self.editing_column = None
        self.event_count = 0

        # Bind double-click
        self.tree.bind("<Double-1>", self._on_double_click)

        # Status
        self.status = tk.Label(
            self.root, text="Double-click on Column 2 to edit", bg="lightgray"
        )
        self.status.pack(fill="x", padx=10, pady=5)

    def log(self, message):
        """Log an event with timestamp."""
        self.event_count += 1
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{self.event_count}] {timestamp} - {message}\n")
        self.log_text.see(tk.END)
        print(f"[{self.event_count}] {message}")

    def _on_double_click(self, event):
        self.log("=== DOUBLE-CLICK ===")
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item or not column:
            return

        col_num = int(column[1:]) - 1
        if col_num != 1:
            return

        values = self.tree.item(item, "values")
        current_value = str(values[col_num])

        self._show_edit_overlay(event, item, column, current_value)

    def _show_edit_overlay(self, event, item, column, current_value):
        self.log("_show_edit_overlay called")

        bbox = self.tree.bbox(item, column)
        if not bbox:
            self.log("ERROR: No bbox")
            return

        cell_x, cell_y, cell_width, cell_height = bbox

        tree_rootx = self.tree.winfo_rootx()
        tree_rooty = self.tree.winfo_rooty()
        root_rootx = self.root.winfo_rootx()
        root_rooty = self.root.winfo_rooty()

        overlay_x = tree_rootx + cell_x - root_rootx
        overlay_y = tree_rooty + cell_y - root_rooty

        self.editing_item = item
        self.editing_column = column

        self.edit_frame.place(
            x=overlay_x, y=overlay_y, width=cell_width, height=cell_height
        )
        self.edit_frame.lift()

        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]
        self.edit_combo.config(values=enum_values, state="readonly")
        self.edit_combo.set(current_value)

        # Unbind all events
        self.edit_combo.unbind("<<ComboboxSelected>>")
        self.edit_combo.unbind("<FocusOut>")
        self.edit_combo.unbind("<FocusIn>")
        self.edit_combo.unbind("<Map>")
        self.edit_combo.unbind("<Unmap>")

        # Bind events with logging
        self.edit_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
        self.edit_combo.bind("<FocusOut>", self._on_focus_out)
        self.edit_combo.bind("<FocusIn>", self._on_focus_in)

        self.edit_combo.focus()
        self.log("Overlay shown, combo focused")

        self.status.config(text="Select a value", bg="lightblue")

    def _on_focus_in(self, event):
        self.log("EVENT: <FocusIn>")

    def _on_combo_selected(self, event):
        self.log("EVENT: <<ComboboxSelected>>")
        new_value = self.edit_combo.get()
        self.log(f"  Selected value: {new_value}")

        # Try to save immediately and see what happens
        self.log("  Attempting to save...")
        self._save_edit()

    def _on_focus_out(self, event):
        self.log("EVENT: <FocusOut>")

    def _save_edit(self):
        self.log("_save_edit called")

        if not self.editing_item or not self.editing_column:
            self.log("  ERROR: No editing context")
            return

        new_value = self.edit_combo.get()
        self.log(f"  Saving value: {new_value}")

        # Update the cell
        item_values = list(self.tree.item(self.editing_item, "values"))
        col_num = int(self.editing_column[1:]) - 1
        item_values[col_num] = new_value
        self.tree.item(self.editing_item, values=item_values)

        self.log("  Cell updated in tree")
        self.status.config(text=f"Saved: {new_value}", bg="lightgreen")

        # Try hiding immediately
        self.log("  Hiding overlay...")
        self._hide_edit_overlay()
        self.log("  Overlay hidden")

    def _hide_edit_overlay(self):
        self.log("_hide_edit_overlay called")
        self.edit_frame.place_forget()
        self.editing_item = None
        self.editing_column = None
        self.log("  Overlay state cleared")

    def run(self):
        print("Debug Dropdown Test - Watch the event log")
        self.root.mainloop()


if __name__ == "__main__":
    app = DebugDropdownTest()
    app.run()
