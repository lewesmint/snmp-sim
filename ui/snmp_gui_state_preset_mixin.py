"""State and preset operations mixin for SNMP GUI."""

# pyright: reportAttributeAccessIssue=false
# ruff: noqa: D101,PLR0915

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, cast

import customtkinter as ctk
import requests


class SNMPGuiStatePresetMixin:
    api_url: str
    root: Any

    def _log(self, message: str, level: str = "INFO") -> None:
        raise NotImplementedError

    def _bake_state(self) -> None:
        """Bake current MIB state into agent-model schema files."""
        try:
            response = messagebox.askyesno(
                "Bake State",
                "This will bake the current MIB state into agent-model schema files,\n"
                "then clear the runtime state file (mib_state.json).\n\n"
                "A backup will be created automatically.\n\n"
                "Continue?",
            )

            if not response:
                return

            self._log("Baking state into schemas...")

            resp = requests.post(f"{self.api_url}/bake-state", timeout=30)
            resp.raise_for_status()
            result = resp.json()

            baked_count = result.get("baked_count", 0)
            backup_dir = result.get("backup_dir", "")

            self._log(f"✓ Baked {baked_count} value(s) into schemas")
            self._log(f"Backup created: {backup_dir}")
            self._log("✓ State file cleared")

            messagebox.showinfo(
                "Success",
                f"Successfully baked {baked_count} value(s) into schemas!\n\n"
                f"Backup: {backup_dir}\n\n"
                "Runtime state file has been cleared.",
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to bake state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error baking state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _fresh_state(self) -> None:
        """Regenerate schemas and empty the MIB state file."""
        try:
            response = messagebox.askyesno(
                "Fresh State",
                "This will regenerate schema files and clear mib_state.json.\n\n"
                "You will need to restart the agent for schema changes to take effect.\n\n"
                "Continue?",
            )
            if not response:
                return

            self._log("Regenerating schemas and clearing state...")
            resp = requests.post(f"{self.api_url}/state/fresh", timeout=60)
            resp.raise_for_status()
            result = resp.json()

            backup_dir = result.get("backup_dir", "")
            regenerated = result.get("regenerated", 0)

            self._log(f"✓ Fresh state complete. Regenerated {regenerated} schema(s)")
            messagebox.showinfo(
                "Success",
                "Fresh State complete.\n\n"
                f"Schemas regenerated: {regenerated}\n"
                f"Backup: {backup_dir}\n\n"
                "Please restart the agent for schema changes to take effect.",
            )
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to run Fresh State: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error during Fresh State: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _reset_state(self) -> None:
        """Clear mib_state.json without regenerating schemas."""
        try:
            response = messagebox.askyesno(
                "Reset State",
                "This will clear mib_state.json (tables, scalars, deleted instances).\n\nContinue?",
            )
            if not response:
                return

            self._log("Resetting state...")
            resp = requests.post(f"{self.api_url}/state/reset", timeout=20)
            resp.raise_for_status()

            self._log("✓ State reset")
            messagebox.showinfo("Success", "State reset completed.")
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to reset state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error resetting state: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _save_preset_dialog(self) -> None:
        """Show dialog to save current agent-model as a preset."""
        try:
            preset_name = simpledialog.askstring(
                "Save Preset",
                "Enter a name for this preset:",
                parent=self.root,
            )

            if not preset_name:
                return

            self._log(f"Saving preset '{preset_name}'...")

            bake_resp = requests.post(f"{self.api_url}/bake-state", timeout=30)
            bake_resp.raise_for_status()

            resp = requests.post(
                f"{self.api_url}/presets/save",
                json={"preset_name": preset_name},
                timeout=30,
            )
            resp.raise_for_status()

            self._log(f"✓ Preset '{preset_name}' saved successfully")

            messagebox.showinfo("Success", f"Preset '{preset_name}' saved successfully!")

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to save preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error saving preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)

    def _load_preset_dialog(self) -> None:
        """Show dialog to load a preset."""
        try:
            resp = requests.get(f"{self.api_url}/presets", timeout=5)
            resp.raise_for_status()
            result = resp.json()

            presets = result.get("presets", [])

            if not presets:
                messagebox.showinfo("No Presets", "No presets available")
                return

            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Load Preset")
            dialog.geometry("400x300")
            dialog.transient(self.root)
            dialog.grab_set()

            ctk.CTkLabel(dialog, text="Select a preset to load:", font=("", 14, "bold")).pack(
                pady=10,
            )

            listbox_frame = ctk.CTkFrame(dialog)
            listbox_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

            scrollbar = ttk.Scrollbar(listbox_frame)
            scrollbar.pack(side="right", fill="y")

            preset_listbox = tk.Listbox(
                listbox_frame,
                yscrollcommand=scrollbar.set,
                font=("", 12),
                bg="#2b2b2b",
                fg="#ffffff",
            )
            preset_listbox.pack(fill="both", expand=True)
            scrollbar.config(command=preset_listbox.yview)

            for preset in presets:
                preset_listbox.insert("end", preset)

            selected_preset: list[str | None] = [None]

            def on_load() -> None:
                selection = cast(
                    "tuple[int, ...]",
                    preset_listbox.curselection(),  # type: ignore[no-untyped-call]
                )
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a preset")
                    return

                selected_preset[0] = presets[selection[0]]
                dialog.destroy()

            def on_cancel() -> None:
                dialog.destroy()

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(pady=10)

            ctk.CTkButton(btn_frame, text="Load", command=on_load, width=100).pack(
                side="left",
                padx=5,
            )
            ctk.CTkButton(btn_frame, text="Cancel", command=on_cancel, width=100).pack(
                side="left",
                padx=5,
            )

            self.root.wait_window(dialog)

            if not selected_preset[0]:
                return

            preset_name = selected_preset[0]

            response = messagebox.askyesno(
                "Load Preset",
                f"This will replace the current agent-model with preset '{preset_name}'.\n\n"
                f"A backup will be created automatically.\n\n"
                f"You will need to restart the agent for changes to take effect.\n\n"
                f"Continue?",
            )

            if not response:
                return

            self._log(f"Loading preset '{preset_name}'...")

            resp = requests.post(
                f"{self.api_url}/presets/load",
                json={"preset_name": preset_name},
                timeout=30,
            )
            resp.raise_for_status()
            _result = resp.json()

            self._log(f"✓ Preset '{preset_name}' loaded successfully")

            messagebox.showinfo(
                "Success",
                f"Preset '{preset_name}' loaded successfully!\n\n"
                f"Please restart the agent for changes to take effect.",
            )

        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to load preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
        except (AttributeError, LookupError, OSError, TypeError, ValueError) as e:
            error_msg = f"Unexpected error loading preset: {e}"
            self._log(error_msg, "ERROR")
            messagebox.showerror("Error", error_msg)
