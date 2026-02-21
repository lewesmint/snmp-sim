#!/usr/bin/env python3
"""
Alternative approach: Use a Listbox popup instead of combobox dropdown.
This avoids the macOS combobox grab issue entirely.
"""

import tkinter as tk
from tkinter import ttk


class AlternativeDropdownTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Alternative Dropdown Test")
        self.root.geometry("600x400")

        # Instructions
        instructions = tk.Label(
            self.root,
            text="Alternative approach: Click on Column 2 cells to edit.\n"
            "This uses a Listbox popup instead of combobox dropdown.",
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

        # State
        self.editing_item = None
        self.editing_column = None
        self.popup_window = None

        # Bind single click (not double-click)
        self.tree.bind("<Button-1>", self._on_click)

        # Status
        self.status = tk.Label(
            self.root,
            text="Click on Column 2 cells to edit",
            bg="lightgray",
            fg="black",
        )
        self.status.pack(fill="x", padx=10, pady=5)

    def _on_click(self, event):
        """Handle click on tree."""
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item or not column:
            return

        col_num = int(column[1:]) - 1
        if col_num != 1:  # Only column 2
            return

        values = self.tree.item(item, "values")
        if col_num >= len(values):
            return

        current_value = str(values[col_num])

        # Get cell bounding box
        bbox = self.tree.bbox(item, column)
        if not bbox:
            return

        self._show_listbox_popup(event, item, column, current_value, bbox)

    def _show_listbox_popup(self, event, item, column, current_value, bbox):
        """Show a listbox popup for selection."""
        # Close any existing popup
        if self.popup_window:
            self.popup_window.destroy()
            self.popup_window = None

        self.editing_item = item
        self.editing_column = column

        cell_x, cell_y, cell_width, cell_height = bbox

        # Get absolute screen coordinates
        tree_rootx = self.tree.winfo_rootx()
        tree_rooty = self.tree.winfo_rooty()

        popup_x = tree_rootx + cell_x
        popup_y = tree_rooty + cell_y + cell_height

        # Create a toplevel window (not a child widget)
        self.popup_window = tk.Toplevel(self.root)
        self.popup_window.wm_overrideredirect(True)  # No window decorations
        self.popup_window.wm_geometry(f"+{popup_x}+{popup_y}")

        # Create listbox
        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]

        listbox = tk.Listbox(
            self.popup_window,
            height=len(enum_values),
            width=max(len(v) for v in enum_values) + 2,
            font=("Helvetica", 12),
        )
        listbox.pack()

        # Populate listbox
        for i, value in enumerate(enum_values):
            listbox.insert(tk.END, value)
            if value == current_value:
                listbox.selection_set(i)
                listbox.see(i)

        # Bind selection
        listbox.bind(
            "<<ListboxSelect>>", lambda e: self._on_listbox_select(listbox, enum_values)
        )
        listbox.bind(
            "<Button-1>", lambda e: self._on_listbox_click(e, listbox, enum_values)
        )

        # Bind focus out to close popup
        self.popup_window.bind("<FocusOut>", lambda e: self._close_popup())

        # Focus the listbox
        listbox.focus_set()

        self.status.config(text="Select a value from the list", bg="lightblue")

    def _on_listbox_click(self, event, listbox, enum_values):
        """Handle click on listbox item."""
        # Get the clicked index
        index = listbox.nearest(event.y)
        if index >= 0 and index < len(enum_values):
            selected_value = enum_values[index]
            print(f"Selected: {selected_value}")
            self._save_value(selected_value)

    def _on_listbox_select(self, listbox, enum_values):
        """Handle listbox selection."""
        selection = listbox.curselection()
        if selection:
            index = selection[0]
            selected_value = enum_values[index]
            print(f"Selected: {selected_value}")
            # Don't save here - wait for click

    def _save_value(self, new_value):
        """Save the selected value."""
        if not self.editing_item or not self.editing_column:
            return

        print(f"Saving: {new_value}")

        # Update the cell
        item_values = list(self.tree.item(self.editing_item, "values"))
        col_num = int(self.editing_column[1:]) - 1
        item_values[col_num] = new_value
        self.tree.item(self.editing_item, values=item_values)

        self.status.config(text=f"✓ Saved: {new_value}", bg="lightgreen")

        # Close popup
        self._close_popup()

    def _close_popup(self):
        """Close the popup window."""
        if self.popup_window:
            self.popup_window.destroy()
            self.popup_window = None

        self.editing_item = None
        self.editing_column = None

    def run(self):
        print("Alternative Dropdown Test - Using Listbox popup")
        self.root.mainloop()


if __name__ == "__main__":
    app = AlternativeDropdownTest()
    app.run()
