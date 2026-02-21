#!/usr/bin/env python3
"""
Test using postcommand to track dropdown state.
"""

import tkinter as tk
from tkinter import ttk


class PostCommandTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PostCommand Dropdown Test")
        self.root.geometry("600x400")

        # Instructions
        instructions = tk.Label(
            self.root,
            text="Test: Use postcommand to track dropdown open/close.\n"
            "Double-click on Column 2 cells to edit.",
            bg="yellow",
            fg="black",
            font=("Helvetica", 11, "bold"),
        )
        instructions.pack(fill="x", padx=10, pady=10)

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
        self.dropdown_is_open = False

        # Bind double-click
        self.tree.bind("<Double-1>", self._on_double_click)

        # Status
        self.status = tk.Label(
            self.root, text="Double-click on Column 2 to edit", bg="lightgray"
        )
        self.status.pack(fill="x", padx=10, pady=5)

    def _on_double_click(self, event):
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

    def _on_dropdown_open(self):
        """Called when dropdown is about to open."""
        print(">>> Dropdown opening")
        self.dropdown_is_open = True

    def _show_edit_overlay(self, event, item, column, current_value):
        print("Showing overlay")

        bbox = self.tree.bbox(item, column)
        if not bbox:
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
        self.dropdown_is_open = False

        self.edit_frame.place(
            x=overlay_x, y=overlay_y, width=cell_width, height=cell_height
        )
        self.edit_frame.lift()

        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]

        # Configure with postcommand
        self.edit_combo.config(
            values=enum_values, state="readonly", postcommand=self._on_dropdown_open
        )
        self.edit_combo.set(current_value)

        # Unbind previous events
        self.edit_combo.unbind("<<ComboboxSelected>>")
        self.edit_combo.unbind("<FocusOut>")

        # Bind events
        self.edit_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._on_combo_selected()
        )
        self.edit_combo.bind("<FocusOut>", lambda e: self._on_focus_out())

        self.edit_combo.focus()
        self.status.config(text="Select a value", bg="lightblue")

    def _on_combo_selected(self):
        print(f">>> ComboboxSelected (dropdown_is_open={self.dropdown_is_open})")
        if not self.editing_item:
            return

        # Mark that dropdown is now closing
        self.dropdown_is_open = False

        # Don't save yet - wait for FocusOut
        print("Waiting for FocusOut...")

    def _on_focus_out(self):
        print(f">>> FocusOut (dropdown_is_open={self.dropdown_is_open})")

        if self.editing_item:
            # Wait a bit to ensure dropdown is fully closed
            print("Scheduling save...")
            self.root.after(200, self._save_edit)

    def _save_edit(self):
        print(">>> Saving...")

        if not self.editing_item or not self.editing_column:
            print("No editing context")
            return

        new_value = self.edit_combo.get()
        print(f"Saving value: {new_value}")

        # Update the cell
        item_values = list(self.tree.item(self.editing_item, "values"))
        col_num = int(self.editing_column[1:]) - 1
        item_values[col_num] = new_value
        self.tree.item(self.editing_item, values=item_values)

        self.status.config(text=f"✓ Saved: {new_value}", bg="lightgreen")
        print("Saved, hiding overlay...")

        # Hide overlay
        self.root.after(200, self._hide_edit_overlay)

    def _hide_edit_overlay(self):
        print(">>> Hiding overlay")
        self.edit_frame.place_forget()
        self.editing_item = None
        self.editing_column = None
        print("Overlay hidden")

    def run(self):
        print("PostCommand Dropdown Test")
        self.root.mainloop()


if __name__ == "__main__":
    app = PostCommandTest()
    app.run()
