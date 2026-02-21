#!/usr/bin/env python3
"""
Minimal test case to reproduce enum dropdown UI lockup issue.
"""

import tkinter as tk
from tkinter import ttk


class TestDropdownGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Dropdown Lockup Test")
        self.root.geometry("600x400")

        # Create treeview with 3 columns
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

        # Add 3 sample rows
        self.tree.insert("", "end", values=("Row 1", "1 (up)", "Value A"))
        self.tree.insert("", "end", values=("Row 2", "2 (down)", "Value B"))
        self.tree.insert("", "end", values=("Row 3", "1 (up)", "Value C"))

        # Create edit overlay (hidden initially)
        self.edit_frame = tk.Frame(self.root, bg="white", relief="solid", borderwidth=1)
        self.edit_combo = ttk.Combobox(self.edit_frame, font=("Helvetica", 12))
        self.edit_combo.pack(padx=2, pady=2, fill="both", expand=True)

        # Editing state
        self.editing_item = None
        self.editing_column = None
        self._saving = False
        self._combo_just_selected = False

        # Bind double-click
        self.tree.bind("<Double-1>", self._on_double_click)

        # Status label
        self.status = tk.Label(
            self.root,
            text="Double-click on Column 2 cells to test enum dropdown",
            bg="yellow",
            fg="black",
        )
        self.status.pack(fill="x", padx=10, pady=5)

    def _on_double_click(self, event):
        """Handle double-click to show edit overlay."""
        # Get clicked cell
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item or not column:
            return

        # Only allow editing column 2 (index 1) - the enum column
        col_num = int(column[1:]) - 1  # #1 -> 0, #2 -> 1, etc
        if col_num != 1:  # Only column 2
            self.status.config(text="Only Column 2 (Enum) is editable", bg="orange")
            return

        values = self.tree.item(item, "values")
        if col_num >= len(values):
            return

        current_value = str(values[col_num])

        # Show edit overlay
        self._show_edit_overlay(event, item, column, current_value)

    def _show_edit_overlay(self, event, item, column, current_value):
        """Show the combobox overlay over the cell."""
        # Hide any existing overlay
        self._hide_edit_overlay()

        # Get cell bounding box
        bbox = self.tree.bbox(item, column)
        if not bbox:
            return

        cell_x, cell_y, cell_width, cell_height = bbox

        # Calculate absolute position
        tree_rootx = self.tree.winfo_rootx()
        tree_rooty = self.tree.winfo_rooty()
        root_rootx = self.root.winfo_rootx()
        root_rooty = self.root.winfo_rooty()

        overlay_x = tree_rootx + cell_x - root_rootx
        overlay_y = tree_rooty + cell_y - root_rooty

        # Store editing state
        self.editing_item = item
        self.editing_column = column

        # Position overlay
        self.edit_frame.place(
            x=overlay_x, y=overlay_y, width=cell_width, height=cell_height
        )
        self.edit_frame.lift()

        # Configure as enum dropdown
        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]
        self.edit_combo.config(values=enum_values, state="readonly")

        # Set current value
        self.edit_combo.set(current_value)
        self.edit_combo.focus()

        # IMPORTANT: Unbind all previous events first to avoid duplicate handlers
        self.edit_combo.unbind("<Return>")
        self.edit_combo.unbind("<Escape>")
        self.edit_combo.unbind("<<ComboboxSelected>>")
        self.edit_combo.unbind("<FocusOut>")

        # Bind events
        self.edit_combo.bind("<Return>", lambda e: self._save_edit())
        self.edit_combo.bind("<Escape>", lambda e: self._hide_edit_overlay())
        self.edit_combo.bind(
            "<<ComboboxSelected>>", lambda e: self._on_combo_selected()
        )
        self.edit_combo.bind("<FocusOut>", lambda e: self._on_focus_out())

        self.status.config(
            text="Select a value from dropdown or press Escape to cancel",
            bg="lightblue",
        )

    def _on_combo_selected(self):
        """Handle combo selection.

        CRITICAL INSIGHT from testing: On macOS, FocusOut fires BEFORE ComboboxSelected!
        By the time we get here, the grab is already released, so we can save immediately.
        """
        if not self.editing_item:
            return

        print("DEBUG: ComboboxSelected event fired - saving immediately")
        self.status.config(text="Combo selected - saving...", bg="lightgreen")

        # Save immediately - the grab is already released by this point
        self._save_edit()

    def _on_focus_out(self):
        """Handle focus leaving combobox.

        On macOS, this fires BEFORE ComboboxSelected, so we don't save here.
        """
        print("DEBUG: FocusOut event fired (happens before ComboboxSelected on macOS)")

    def _save_edit(self):
        """Save the edited value."""
        if not self.editing_item or not self.editing_column or self._saving:
            print("DEBUG: Save blocked - already saving or no edit active")
            return

        self._saving = True
        print("DEBUG: Save started")

        try:
            new_value = self.edit_combo.get()
            print(f"DEBUG: Got value: {new_value}")

            # Update the cell
            item_values = list(self.tree.item(self.editing_item, "values"))
            col_num = int(self.editing_column[1:]) - 1
            item_values[col_num] = new_value
            self.tree.item(self.editing_item, values=item_values)

            self.status.config(text=f"Saved: {new_value}", bg="lightgreen")
            print("DEBUG: Save complete")
        except Exception as e:
            self.status.config(text=f"Error: {e}", bg="red")
            print(f"DEBUG: Save error: {e}")
        finally:
            print("DEBUG: Entering finally block")
            self._saving = False
            self._combo_just_selected = False

            # FIXED: Use a delay to hide the overlay. This ensures the combobox
            # dropdown has fully closed and released its grab before we hide the widget.
            # On macOS, after_idle is not sufficient - we need a real time delay.
            self.root.after(150, self._hide_edit_overlay)

            print("DEBUG: Finally block complete")

    def _hide_edit_overlay(self):
        """Hide the edit overlay."""
        print("DEBUG: Hide called")

        # Hide overlay
        self.edit_frame.place_forget()

        # Clear state
        self.editing_item = None
        self.editing_column = None

        # DON'T try to set focus - let tkinter handle it

        print("DEBUG: Hide complete")

    def run(self):
        """Run the GUI."""
        print("Double-click on Column 2 cells to test enum dropdown")
        print("Watch console for DEBUG messages")
        print("If UI locks up, click on another window to unlock it")
        self.root.mainloop()


if __name__ == "__main__":
    app = TestDropdownGUI()
    app.run()
