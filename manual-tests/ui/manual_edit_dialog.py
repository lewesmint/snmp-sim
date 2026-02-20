#!/usr/bin/env python3
"""Test script for the edit dialog functionality."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import customtkinter as ctk
from ui.snmp_gui import SNMPControllerGUI

def test_edit_dialog() -> None:
    """Test the edit dialog with different writable states."""
    root = ctk.CTk()
    app = SNMPControllerGUI(root)

    # Mock some metadata for testing
    app.oid_metadata = {
        "1.3.6.1.2.1.1.1": {"type": "DisplayString", "access": "readonly"},
        "1.3.6.1.2.1.1.4": {"type": "DisplayString", "access": "read-write"}
    }

    print("Testing edit dialog...")

    # Test 1: Read-only OID (should show checkbox)
    print("\n=== Test 1: Read-only OID (sysDescr) ===")
    app._show_edit_dialog("1.3.6.1.2.1.1.1.0", "Test system description", "dummy_item", False)

    print("First dialog should be open. Check if checkbox appears.")
    print("Press Enter to continue to next test...")

    # Wait for user input
    input()

    # Test 2: Writable OID (should NOT show checkbox)
    print("\n=== Test 2: Writable OID (sysContact) ===")
    app._show_edit_dialog("1.3.6.1.2.1.1.4.0", "admin@example.com", "dummy_item", True)

    print("Second dialog should be open. Check if NO checkbox appears.")

    root.mainloop()

if __name__ == "__main__":
    test_edit_dialog()