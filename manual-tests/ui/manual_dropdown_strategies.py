#!/usr/bin/env python3
"""
Test different strategies for handling combobox dropdown on macOS.
"""

import tkinter as tk
from tkinter import ttk


class StrategyTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Dropdown Strategy Test")
        self.root.geometry("800x600")

        # Instructions
        instructions = tk.Label(
            self.root,
            text="Test different strategies for handling dropdown selection.\n"
            "Double-click on cells in Column 2 to edit.",
            bg="yellow",
            fg="black",
            font=("Helvetica", 12, "bold"),
        )
        instructions.pack(fill="x", padx=10, pady=10)

        # Strategy selector
        strategy_frame = tk.Frame(self.root)
        strategy_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(strategy_frame, text="Strategy:", font=("Helvetica", 11, "bold")).pack(
            side="left"
        )

        self.strategy_var = tk.StringVar(value="strategy3")
        strategies = [
            ("1: Save on ComboboxSelected (immediate)", "strategy1"),
            ("2: Save on ComboboxSelected (after_idle)", "strategy2"),
            ("3: Save on FocusOut only", "strategy3"),
            ("4: Save on ComboboxSelected + close dropdown", "strategy4"),
        ]

        for text, value in strategies:
            rb = tk.Radiobutton(
                strategy_frame,
                text=text,
                variable=self.strategy_var,
                value=value,
                font=("Helvetica", 10),
            )
            rb.pack(side="left", padx=5)

        # Create treeview
        self.tree = ttk.Treeview(
            self.root, columns=("col1", "col2", "col3"), show="headings"
        )
        self.tree.heading("col1", text="Column 1")
        self.tree.heading("col2", text="Column 2 (Enum)")
        self.tree.heading("col3", text="Column 3")

        self.tree.column("col1", width=200)
        self.tree.column("col2", width=250)
        self.tree.column("col3", width=200)

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
        self._saving = False
        self._combo_just_selected = False

        # Bind double-click
        self.tree.bind("<Double-1>", self._on_double_click)

        # Status
        self.status = tk.Label(
            self.root, text="Ready", bg="lightgray", fg="black", font=("Helvetica", 10)
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
        if col_num != 1:  # Only column 2
            self.status.config(text="Only Column 2 is editable", bg="orange")
            return

        values = self.tree.item(item, "values")
        if col_num >= len(values):
            return

        current_value = str(values[col_num])
        self._show_edit_overlay(event, item, column, current_value)

    def _show_edit_overlay(self, event, item, column, current_value):
        self._hide_edit_overlay()

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

        self.edit_frame.place(
            x=overlay_x, y=overlay_y, width=cell_width, height=cell_height
        )
        self.edit_frame.lift()

        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]
        self.edit_combo.config(values=enum_values, state="readonly")
        self.edit_combo.set(current_value)
        self.edit_combo.focus()

        # Unbind previous events
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

        strategy = self.strategy_var.get()
        self.status.config(text=f"Using {strategy} - Select a value", bg="lightblue")

    def _on_combo_selected(self):
        if not self.editing_item:
            return

        print(f"\n>>> ComboboxSelected event - Strategy: {self.strategy_var.get()}")
        self._combo_just_selected = True

        strategy = self.strategy_var.get()

        if strategy == "strategy1":
            # Strategy 1: Save immediately
            print("Strategy 1: Saving immediately")
            self._save_edit()
        elif strategy == "strategy2":
            # Strategy 2: Save with after_idle
            print("Strategy 2: Saving with after_idle")
            self.root.after_idle(self._save_edit)
        elif strategy == "strategy3":
            # Strategy 3: Don't save here, let FocusOut handle it
            print("Strategy 3: Waiting for FocusOut")
            pass
        elif strategy == "strategy4":
            # Strategy 4: Close dropdown first, then save
            print("Strategy 4: Closing dropdown, then saving")
            self.edit_combo.selection_clear()
            self.tree.focus_set()
            self.root.after(100, self._save_edit)

    def _on_focus_out(self):
        print(f">>> FocusOut event - combo_just_selected={self._combo_just_selected}")

        strategy = self.strategy_var.get()

        if strategy in ["strategy1", "strategy2", "strategy4"]:
            # For these strategies, ignore FocusOut if combo was just selected
            if self._combo_just_selected:
                print("FocusOut: Ignoring (combo was just selected)")
                return

        # Strategy 3 or fallback: Save on FocusOut
        if self.editing_item:
            print("FocusOut: Triggering save")
            self.root.after(50, self._save_edit)

    def _save_edit(self):
        if not self.editing_item or not self.editing_column or self._saving:
            print("Save blocked")
            return

        self._saving = True
        print(">>> Save started")

        try:
            new_value = self.edit_combo.get()
            print(f"Saving value: {new_value}")

            item_values = list(self.tree.item(self.editing_item, "values"))
            col_num = int(self.editing_column[1:]) - 1
            item_values[col_num] = new_value
            self.tree.item(self.editing_item, values=item_values)

            self.status.config(text=f"✓ Saved: {new_value}", bg="lightgreen")
            print("Save complete")
        except Exception as e:
            self.status.config(text=f"✗ Error: {e}", bg="red")
            print(f"Save error: {e}")
        finally:
            print(">>> Hiding overlay")
            self._saving = False
            self._combo_just_selected = False
            self.root.after(100, self._hide_edit_overlay)

    def _hide_edit_overlay(self):
        print(">>> Hide overlay")
        self.edit_frame.place_forget()
        self.editing_item = None
        self.editing_column = None

    def run(self):
        print("Dropdown Strategy Test")
        print("Try each strategy and see which one works best on your platform")
        self.root.mainloop()


if __name__ == "__main__":
    app = StrategyTest()
    app.run()
