#!/usr/bin/env python3
"""
Automated test for dropdown lockup issue.
This script simulates user interactions to test if the dropdown causes UI lockup.
"""

import tkinter as tk
from tkinter import ttk
import sys


class AutomatedDropdownTest:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Automated Dropdown Test")
        self.root.geometry("600x400")
        
        # Create treeview with 3 columns
        self.tree = ttk.Treeview(self.root, columns=("col1", "col2", "col3"), show="headings")
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
        
        # Test state
        self.test_count = 0
        self.max_tests = 5
        self.test_passed = True
        self.test_results = []
        
        # Status label
        self.status = tk.Label(self.root, text="Starting automated test...", 
                               bg="yellow", fg="black")
        self.status.pack(fill="x", padx=10, pady=5)
        
        # Start automated test after UI is ready
        self.root.after(500, self.run_automated_test)
        
    def run_automated_test(self):
        """Run automated test sequence."""
        if self.test_count >= self.max_tests:
            self.finish_test()
            return
        
        self.test_count += 1
        print(f"\n=== Test {self.test_count}/{self.max_tests} ===")
        self.status.config(text=f"Running test {self.test_count}/{self.max_tests}...", bg="lightblue")
        
        # Get first item
        items = self.tree.get_children()
        if not items:
            print("ERROR: No items in tree")
            self.test_passed = False
            self.finish_test()
            return
        
        item = items[0]
        
        # Simulate double-click on column 2
        self.root.after(100, lambda: self.simulate_edit(item))
    
    def simulate_edit(self, item):
        """Simulate editing a cell."""
        print("Simulating edit...")
        
        # Get cell bounding box
        bbox = self.tree.bbox(item, "#2")  # Column 2
        if not bbox:
            print("ERROR: Could not get bbox")
            self.test_passed = False
            self.finish_test()
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
        self.editing_column = "#2"
        
        # Position overlay
        self.edit_frame.place(x=overlay_x, y=overlay_y, width=cell_width, height=cell_height)
        self.edit_frame.lift()
        
        # Configure as enum dropdown
        enum_values = ["1 (up)", "2 (down)", "3 (testing)"]
        self.edit_combo.config(values=enum_values, state="readonly")
        
        # Set current value
        values = self.tree.item(item, "values")
        current_value = str(values[1])
        self.edit_combo.set(current_value)
        self.edit_combo.focus()
        
        # Unbind previous events
        self.edit_combo.unbind("<<ComboboxSelected>>")
        self.edit_combo.unbind("<FocusOut>")
        
        # Bind events
        self.edit_combo.bind("<<ComboboxSelected>>", lambda e: self._on_combo_selected())
        self.edit_combo.bind("<FocusOut>", lambda e: self._on_focus_out())
        
        # Simulate selecting a different value after a short delay
        self.root.after(200, self.simulate_selection)
    
    def simulate_selection(self):
        """Simulate selecting a value from dropdown."""
        print("Simulating selection...")
        
        # Change to a different value
        current = self.edit_combo.get()
        if "1 (up)" in current:
            new_value = "2 (down)"
        else:
            new_value = "1 (up)"
        
        self.edit_combo.set(new_value)
        
        # Trigger the selection event
        self.edit_combo.event_generate("<<ComboboxSelected>>")

        # Schedule next test
        self.root.after(500, self.run_automated_test)

    def _on_combo_selected(self):
        """Handle combo selection."""
        if not self.editing_item:
            return

        print("Combo selected - saving...")
        self._combo_just_selected = True

        # FIXED: Use after_idle to let the combobox complete its internal state changes
        self.root.after_idle(self._save_edit)

    def _on_focus_out(self):
        """Handle focus leaving combobox."""
        if self._combo_just_selected:
            self._combo_just_selected = False
            return

        if self.editing_item:
            self.root.after_idle(self._save_edit)

    def _save_edit(self):
        """Save the edited value."""
        if not self.editing_item or not self.editing_column or self._saving:
            print("Save blocked - already saving or no edit active")
            return

        self._saving = True
        print("Save started")

        try:
            new_value = self.edit_combo.get()
            print(f"Got value: {new_value}")

            # Update the cell
            item_values = list(self.tree.item(self.editing_item, "values"))
            col_num = int(self.editing_column[1:]) - 1
            item_values[col_num] = new_value
            self.tree.item(self.editing_item, values=item_values)

            self.status.config(text=f"Test {self.test_count}: Saved {new_value}", bg="lightgreen")
            print("Save complete")

            # Record successful test
            self.test_results.append(f"Test {self.test_count}: PASS - Saved {new_value}")

        except Exception as e:
            self.status.config(text=f"Test {self.test_count}: Error - {e}", bg="red")
            print(f"Save error: {e}")
            self.test_passed = False
            self.test_results.append(f"Test {self.test_count}: FAIL - {e}")
        finally:
            print("Entering finally block")
            self._saving = False
            self._combo_just_selected = False

            # FIXED: Use after_idle to hide the overlay
            self.root.after_idle(self._hide_edit_overlay)

            print("Finally block complete")

    def _hide_edit_overlay(self):
        """Hide the edit overlay."""
        print("Hide called")

        # Hide overlay
        self.edit_frame.place_forget()

        # Clear state
        self.editing_item = None
        self.editing_column = None

        print("Hide complete")

    def finish_test(self):
        """Finish the test and display results."""
        print("\n" + "="*50)
        print("AUTOMATED TEST RESULTS")
        print("="*50)

        for result in self.test_results:
            print(result)

        if self.test_passed and len(self.test_results) == self.max_tests:
            print("\n✓ ALL TESTS PASSED - No UI lockup detected!")
            self.status.config(text="✓ All tests passed - No lockup!", bg="lightgreen")
            exit_code = 0
        else:
            print("\n✗ TESTS FAILED")
            self.status.config(text="✗ Tests failed", bg="red")
            exit_code = 1

        print("="*50)

        # Close window after 3 seconds
        self.root.after(3000, lambda: self.root.quit())
        self.root.after(3100, lambda: sys.exit(exit_code))

    def run(self):
        """Run the GUI."""
        print("Starting automated dropdown test...")
        print("This will test dropdown selection 5 times")
        self.root.mainloop()


if __name__ == "__main__":
    app = AutomatedDropdownTest()
    app.run()


