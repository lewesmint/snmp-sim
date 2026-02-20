#!/usr/bin/env python3
"""
Test script to verify table display changes in SNMP GUI.
Tests that tables show entries (like sysOREntry.1) under the table, and columns grouped under each entry.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ui.snmp_gui import SNMPControllerGUI
import customtkinter as ctk
import time

def test_table_display() -> bool:
    """Test that table display shows column instances directly under the table."""

    # Create GUI instance
    root = ctk.CTk()
    gui = SNMPControllerGUI(root, api_url="http://127.0.0.1:8800")

    # Wait for connection and data loading
    print("Waiting for GUI to connect and load data...")
    max_wait = 10
    for i in range(max_wait):
        if gui.connected:
            break
        time.sleep(1)
        root.update()

    if not gui.connected:
        print("ERROR: GUI failed to connect to API")
        return False

    # Wait for OID tree to populate
    print("Waiting for OID tree to populate...")
    time.sleep(2)
    root.update()

    # Find table nodes
    table_nodes = []
    def find_tables(item: str = "") -> None:
        if not item:
            item = gui.oid_tree.get_children()[0] if gui.oid_tree.get_children() else ""

        for child in gui.oid_tree.get_children(item):
            tags = gui.oid_tree.item(child, 'tags')
            if 'table' in tags:
                table_nodes.append(child)
            find_tables(child)

    find_tables()

    if not table_nodes:
        print("ERROR: No table nodes found in OID tree")
        return False

    print(f"Found {len(table_nodes)} table nodes")

    # Check one table node by expanding it
    table_node = table_nodes[0]  # Test the first table
    table_text = gui.oid_tree.item(table_node, 'text')
    print(f"Testing table: {table_text}")

    # Initially should have no children
    initial_children = gui.oid_tree.get_children(table_node)
    if len(initial_children) != 0:
        print(f"ERROR: Table {table_text} initially has {len(initial_children)} children, expected 0")
        return False

    # Expand the table (this should trigger _discover_table_instances)
    gui.oid_tree.item(table_node, open=True)
    # Wait for background task to complete
    time.sleep(3)
    root.update()

    # Now check children
    children = gui.oid_tree.get_children(table_node)
    if len(children) == 0:
        print(f"ERROR: Table {table_text} has no children after expansion")
        return False

    print(f"Table {table_text} has {len(children)} children after expansion")

    # Check that children are entry instances (should have names like "sysOREntry.1", "sysOREntry.2", etc.)
    expected_entry_pattern = 'sysOREntry.'  # Should have "sysOREntry.X"
    found_entries = False
    for child in children:
        child_text = gui.oid_tree.item(child, 'text')
        print(f"  Child: {child_text}")
        if expected_entry_pattern in child_text and any(char.isdigit() for char in child_text):
            found_entries = True
            # Test expanding one entry
            gui.oid_tree.item(child, open=True)
            time.sleep(1)
            root.update()
            entry_children = gui.oid_tree.get_children(child)
            if len(entry_children) == 0:
                print(f"ERROR: Entry {child_text} has no children after expansion")
                return False
            print(f"    Entry {child_text} has {len(entry_children)} column children")
            # Check column display format
            for col_child in entry_children:
                col_text = gui.oid_tree.item(col_child, 'text')
                print(f"      Column: {col_text}")
                if " (instance = " in col_text:
                    print(f"ERROR: Column {col_text} should not have '(instance = X)' in the name")
                    return False
            break  # Test only one entry

    if not found_entries:
        print("ERROR: Table children don't appear to be entry instances")
        return False

    print("SUCCESS: Table display shows entries with columns grouped under them!")
    return True

if __name__ == "__main__":
    try:
        success = test_table_display()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: Test failed with exception: {e}")
        sys.exit(1)