#!/usr/bin/env python3
"""
Test: Don't hide the overlay, just move it off-screen.
This might avoid the grab issue.
"""

import tkinter as tk
from tkinter import ttk


class NoHideDropdownTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("No-Hide Dropdown Test")
        self.root.geometry("600x400")
        
        # Instructions
        instructions = tk.Label(
            self.root,
            text="Test: Overlay is never hidden, just moved off-screen.\n"
                 "Double-click on Column 2 cells to edit.",
            bg="yellow",
            fg="black",
            font=("Helvetica", 11, "bold")
        )
        instructions.pack(fill="x", padx=10, pady=10)
        
        # Create treeview
        self.tree = ttk.Treeview(self.root, columns=("col1", "col2", "col3"), show="headings")
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
        
        # Create edit overlay - keep it persistent
        self.edit_frame = tk.Frame(self.root, bg="white", relief="solid", borderwidth=1)
        self.edit_combo = ttk.Combobox(self.edit_frame, font=("Helvetica", 12))
        self.edit_combo.pack(padx=2, pady=2, fill="both", expand=True)
        
        # Start it off-screen
        self.edit_frame.place(x=-1000, y=-1000, width=100, height=30)
        
        # State
        self.editing_item = None
        self.editing_column = None
        
        # Bind double-click
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # Status
        self.status = tk.Label(self.root, text="Double-click on Column 2 to edit", bg="lightgray")
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
        
        # Move overlay to position (don't hide/show, just move)
        self.edit_frame.place(x=overlay_x, y=overlay_y, width=cell_width, height=cell_height)
        self.edit_frame.lift()
        
        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]
        self.edit_combo.config(values=enum_values, state="readonly")
        self.edit_combo.set(current_value)
        
        # Unbind previous events
        self.edit_combo.unbind("<<ComboboxSelected>>")
        self.edit_combo.unbind("<FocusOut>")
        
        # Bind events
        self.edit_combo.bind("<<ComboboxSelected>>", lambda e: self._on_combo_selected())
        self.edit_combo.bind("<FocusOut>", lambda e: self._on_focus_out())
        
        self.edit_combo.focus()
        self.status.config(text="Select a value", bg="lightblue")
    
    def _on_combo_selected(self):
        print("ComboboxSelected event")
        if not self.editing_item:
            return
        
        # Save immediately
        self._save_edit()
    
    def _on_focus_out(self):
        print("FocusOut event")
        # Move overlay off-screen when focus is lost
        self.root.after(100, self._hide_edit_overlay)
    
    def _save_edit(self):
        print("Saving...")
        
        if not self.editing_item or not self.editing_column:
            return
        
        new_value = self.edit_combo.get()
        print(f"Saving value: {new_value}")
        
        # Update the cell
        item_values = list(self.tree.item(self.editing_item, "values"))
        col_num = int(self.editing_column[1:]) - 1
        item_values[col_num] = new_value
        self.tree.item(self.editing_item, values=item_values)
        
        self.status.config(text=f"✓ Saved: {new_value}", bg="lightgreen")
        print("Saved")
        
        # Move overlay off-screen (don't destroy it)
        self.root.after(100, self._hide_edit_overlay)
    
    def _hide_edit_overlay(self):
        print("Moving overlay off-screen")
        # Don't use place_forget() - just move it off-screen
        self.edit_frame.place(x=-1000, y=-1000, width=100, height=30)
        self.editing_item = None
        self.editing_column = None
        print("Overlay moved")
    
    def run(self):
        print("No-Hide Dropdown Test")
        print("Overlay is never destroyed, just moved off-screen")
        self.root.mainloop()


if __name__ == "__main__":
    app = NoHideDropdownTest()
    app.run()

