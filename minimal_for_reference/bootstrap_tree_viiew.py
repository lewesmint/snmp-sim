from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Dict, Optional, Union, cast

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, LEFT, RIGHT, X
from ttkbootstrap_icons_bs import BootstrapIcon

TreeImage = Union[tk.PhotoImage, str]


@dataclass(frozen=True)
class NodeType:
    key: str
    label: str
    icon_name: str


NODE_TYPES = [
    NodeType("folder", "Folder", "folder"),
    NodeType("file", "File", "file-earmark-text"),
    NodeType("server", "Server", "hdd-network"),
    NodeType("client", "Client", "pc-display"),
    NodeType("warning", "Warning", "exclamation-triangle"),
]


class IconTreeDemo:
    def __init__(self) -> None:
        self.root = tb.Window(themename="darkly")
        self.root.title("Treeview icon demo (readable fonts + themed icons)")
        self.root.geometry("980x560")

        self.icon_size = 24

        # Cache PhotoImages to keep them alive
        self.icon_cache: Dict[str, tk.PhotoImage] = {}

        self._configure_styles()
        self._build_ui()
        self._populate_demo_tree()

    def _configure_styles(self) -> None:
        style: tb.Style = tb.Style()  # type: ignore[no-untyped-call]

        # Larger default font for the whole app (macOS defaults can be tiny)
        base_font = ("Helvetica", 14)
        style.configure(".", font=base_font)

        # Make Treeview readable and increase row height
        style.configure("Treeview", font=base_font, rowheight=32)
        style.configure("Treeview.Heading", font=("Helvetica", 14, "bold"))

        # Make buttons/entries readable too
        style.configure("TButton", font=base_font)
        style.configure("TLabel", font=base_font)
        style.configure("TEntry", font=base_font)
        style.configure("TCombobox", font=base_font)

        # Pick a light icon colour for dark background
        # Use a light grey rather than pure white to reduce glare
        self.icon_colour = "#d7d7d7"

    def _build_ui(self) -> None:
        top = tb.Frame(self.root, padding=12)
        top.pack(fill=X)

        tb.Label(top, text="Node type:").pack(side=LEFT)

        self.node_type_var = tk.StringVar(value=NODE_TYPES[0].key)
        type_values = [nt.key for nt in NODE_TYPES]
        tb.Combobox(
            top,
            textvariable=self.node_type_var,
            values=type_values,
            width=18,
            state="readonly",
        ).pack(side=LEFT, padx=(8, 16))

        tb.Label(top, text="Label:").pack(side=LEFT)
        self.label_var = tk.StringVar(value="New item")
        tb.Entry(top, textvariable=self.label_var, width=30).pack(
            side=LEFT, padx=(8, 16)
        )

        tb.Button(
            top, text="Add child", bootstyle="success", command=self.add_child
        ).pack(side=LEFT, padx=(0, 8))
        tb.Button(
            top, text="Add sibling", bootstyle="info", command=self.add_sibling
        ).pack(side=LEFT, padx=(0, 8))
        tb.Button(
            top, text="Rename", bootstyle="warning", command=self.rename_selected
        ).pack(side=LEFT, padx=(0, 8))
        tb.Button(
            top, text="Delete", bootstyle="danger", command=self.delete_selected
        ).pack(side=LEFT)

        main = tb.Frame(self.root, padding=(12, 0, 12, 12))
        main.pack(fill=BOTH, expand=True)

        # Add a Type column so the UI feels less cramped and more informative
        self.tree = tb.Treeview(
            main,
            columns=("type",),
            show="tree headings",
            bootstyle="info",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("#0", width=640, stretch=True)
        self.tree.column("type", width=220, stretch=False, anchor="w")

        yscroll = tb.Scrollbar(main, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=RIGHT, fill="y")

        self.tree.bind("<Double-1>", self._toggle_open)
        self.tree.bind("<<TreeviewSelect>>", self._sync_controls_from_selection)

    @staticmethod
    def _node_type(key: str) -> Optional[NodeType]:
        return next((nt for nt in NODE_TYPES if nt.key == key), None)

    def _get_icon(self, node_type_key: str) -> Optional[tk.PhotoImage]:
        cached = self.icon_cache.get(node_type_key)
        if cached is not None:
            return cached

        nt = self._node_type(node_type_key)
        if nt is None:
            return None

        icon_obj = BootstrapIcon(
            nt.icon_name, size=self.icon_size, color=self.icon_colour
        )
        image = cast(tk.PhotoImage, icon_obj.image)

        self.icon_cache[node_type_key] = image
        return image

    def _tree_image(self, node_type_key: str) -> TreeImage:
        image = self._get_icon(node_type_key)
        return image if image is not None else ""

    def _insert(
        self, parent: str, text: str, node_type_key: str, open_item: bool = False
    ) -> str:
        nt = self._node_type(node_type_key)
        type_label = nt.label if nt else node_type_key

        return self.tree.insert(
            parent,
            "end",
            text=text,
            image=self._tree_image(node_type_key),
            values=(type_label,),
            open=open_item,
            tags=(node_type_key,),
        )

    def _populate_demo_tree(self) -> None:
        root_folder = self._insert("", "Project", "folder", open_item=True)

        src = self._insert(root_folder, "src", "folder", open_item=True)
        self._insert(src, "app.py", "file")
        self._insert(src, "widgets.py", "file")

        assets = self._insert(root_folder, "assets", "folder")
        self._insert(assets, "logo.png", "file")

        infra = self._insert(root_folder, "infra", "folder", open_item=True)
        server = self._insert(infra, "server-01", "server", open_item=True)
        self._insert(server, "client-a", "client")
        self._insert(server, "client-b", "client")
        self._insert(infra, "backup warning", "warning")

        self.tree.selection_set(root_folder)

    def _selected(self) -> Optional[str]:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def add_child(self) -> None:
        parent = self._selected() or ""
        node_type_key = self.node_type_var.get()
        text = self.label_var.get().strip() or "Untitled"

        new_id = self._insert(parent, text, node_type_key, open_item=False)
        self.tree.selection_set(new_id)
        self.tree.see(new_id)

    def add_sibling(self) -> None:
        selected = self._selected()
        if selected is None:
            self.add_child()
            return

        parent = self.tree.parent(selected)
        node_type_key = self.node_type_var.get()
        text = self.label_var.get().strip() or "Untitled"

        new_id = self._insert(parent, text, node_type_key, open_item=False)
        self.tree.selection_set(new_id)
        self.tree.see(new_id)

    def rename_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        text = self.label_var.get().strip() or "Untitled"
        self.tree.item(selected, text=text)

    def delete_selected(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        parent = self.tree.parent(selected)
        self.tree.delete(selected)
        if parent:
            self.tree.selection_set(parent)

    def _toggle_open(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self._selected()
        if selected is None:
            return
        is_open = bool(self.tree.item(selected, "open"))
        self.tree.item(selected, open=not is_open)

    def _sync_controls_from_selection(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self._selected()
        if selected is None:
            return

        self.label_var.set(str(self.tree.item(selected, "text")))

        tags = self.tree.item(selected, "tags")
        if tags:
            self.node_type_var.set(str(tags[0]))

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    IconTreeDemo().run()


if __name__ == "__main__":
    main()
