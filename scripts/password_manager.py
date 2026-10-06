"""Open the Matrix local password manager backed by Windows Credential Manager."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    if sys.platform != "win32":
        print("The Matrix local password manager requires Windows.", file=sys.stderr)
        return 2

    import tkinter as tk
    from tkinter import messagebox, ttk

    from windows_credential_store import CredentialStoreError, WindowsCredentialStore

    try:
        store = WindowsCredentialStore()
    except CredentialStoreError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    root = tk.Tk()
    root.title("Matrix Local Password Manager")
    root.geometry("820x560")
    root.minsize(680, 440)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    ttk.Label(
        root,
        text="Passwords are saved in Windows Credential Manager for this signed-in Windows account. "
             "There is no extra master password.",
        wraplength=780,
    ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

    frame = ttk.Frame(root, padding=12)
    frame.grid(row=1, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    columns = ("label", "username", "notes")
    tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
    for key, heading, width in (
        ("label", "Service / account", 220), ("username", "Username", 220), ("notes", "Notes", 300),
    ):
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor="w")
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    status = tk.StringVar(value="Ready")
    ttk.Label(root, textvariable=status, anchor="w").grid(row=2, column=0, sticky="ew", padx=12, pady=6)

    entries: dict[str, dict] = {}

    def refresh():
        try:
            rows = store.list_entries()
        except CredentialStoreError as exc:
            messagebox.showerror("Password manager", str(exc), parent=root)
            return
        entries.clear()
        tree.delete(*tree.get_children())
        for row in rows:
            entries[row["id"]] = row
            tree.insert("", "end", iid=row["id"], values=(
                row["label"], row["username"], row["notes"],
            ))
        status.set(f"{len(rows)} saved credential(s). Passwords are hidden until you choose Reveal.")

    def selected() -> dict | None:
        selection = tree.selection()
        return entries.get(selection[0]) if selection else None

    def edit(entry: dict | None = None):
        full_entry = None
        if entry:
            try:
                full_entry = store.read(entry["id"])
            except CredentialStoreError as exc:
                messagebox.showerror("Password manager", str(exc), parent=root)
                return
            if not full_entry:
                status.set("Credential no longer exists in Windows Credential Manager.")
                refresh()
                return
        dialog = tk.Toplevel(root)
        dialog.title("Edit credential" if entry else "Add credential")
        dialog.transient(root)
        dialog.grab_set()
        dialog.columnconfigure(1, weight=1)
        fields = {}
        for row, (key, label, masked) in enumerate((
            ("label", "Service / account", False),
            ("username", "Username", False),
            ("password", "Password", True),
            ("notes", "Notes", False),
        )):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=7)
            field = ttk.Entry(dialog, show="*" if masked else "")
            field.grid(row=row, column=1, sticky="ew", padx=12, pady=7)
            if entry and key != "password":
                field.insert(0, entry.get(key, ""))
            if entry and key == "password":
                field.insert(0, full_entry.get("password", ""))
            fields[key] = field

        def save():
            try:
                store.save(
                    entry_id=entry["id"] if entry else None,
                    label=fields["label"].get(), username=fields["username"].get(),
                    password=fields["password"].get(), notes=fields["notes"].get(),
                )
            except (CredentialStoreError, ValueError) as exc:
                messagebox.showerror("Could not save credential", str(exc), parent=dialog)
                return
            status.set("Credential saved to Windows Credential Manager.")
            dialog.destroy()
            refresh()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=5)
        ttk.Button(buttons, text="Save", command=save).pack(side="right")
        dialog.bind("<Return>", lambda _event: save())
        fields["label"].focus_set()

    def reveal():
        entry = selected()
        if not entry:
            messagebox.showinfo("Reveal password", "Select a credential first.", parent=root)
            return
        try:
            full = store.read(entry["id"])
        except CredentialStoreError as exc:
            messagebox.showerror("Password manager", str(exc), parent=root)
            return
        if not full:
            status.set("Credential no longer exists in Windows Credential Manager.")
            refresh()
            return
        if not messagebox.askyesno(
            "Copy saved password",
            f"Copy the password for {full['label']} to the Windows clipboard?",
            parent=root,
        ):
            return
        root.clipboard_clear()
        root.clipboard_append(full["password"])
        status.set("Password copied to clipboard. Clear the clipboard after use.")

    def delete():
        entry = selected()
        if not entry:
            messagebox.showinfo("Delete credential", "Select a credential first.", parent=root)
            return
        if not messagebox.askyesno(
            "Delete saved credential",
            f"Delete the Windows Credential Manager entry for {entry['label']}?",
            parent=root,
        ):
            return
        try:
            store.delete(entry["id"])
        except CredentialStoreError as exc:
            messagebox.showerror("Password manager", str(exc), parent=root)
            return
        status.set("Credential deleted.")
        refresh()

    buttons = ttk.Frame(root, padding=(12, 0, 12, 12))
    buttons.grid(row=3, column=0, sticky="ew")
    ttk.Button(buttons, text="Add", command=lambda: edit()).pack(side="left", padx=(0, 6))
    ttk.Button(buttons, text="Edit", command=lambda: edit(selected()) if selected() else
               messagebox.showinfo("Edit credential", "Select a credential first.", parent=root)).pack(side="left", padx=6)
    ttk.Button(buttons, text="Copy password", command=reveal).pack(side="left", padx=6)
    ttk.Button(buttons, text="Delete", command=delete).pack(side="left", padx=6)
    ttk.Button(buttons, text="Refresh", command=refresh).pack(side="right")
    tree.bind("<Double-1>", lambda _event: edit(selected()) if selected() else None)
    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
