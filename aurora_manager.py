"""Local desktop manager for read-only data checks and private review exports."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from scripts.vault_product_files import (
    LOCAL_OUTPUT,
    build_reconciliation,
    write_reconciliation,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_PRODUCT_FILES = Path.home() / "Desktop" / "Vault" / "product_files"


class AuroraManager(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Aurora Local Manager")
        self.geometry("860x640")
        self.minsize(720, 500)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.current_report = None
        self.product_files = tk.StringVar(
            value=str(DEFAULT_PRODUCT_FILES if DEFAULT_PRODUCT_FILES.is_dir() else "")
        )
        self.status = tk.StringVar(value="Ready — local-only mode; no model or network calls.")
        self._build()
        self.after(100, self._drain_events)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(14, 12))
        header.pack(fill="x")
        ttk.Label(header, text="Aurora Local Manager", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=f"Workspace: {ROOT}  ·  Files and reports stay local",
            wraplength=820,
        ).pack(anchor="w", pady=(5, 0))

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12)
        mapping_tab = ttk.Frame(tabs, padding=14)
        workflow_tab = ttk.Frame(tabs, padding=14)
        tabs.add(mapping_tab, text="Product files")
        tabs.add(workflow_tab, text="Local workflows")
        self._build_mapping_tab(mapping_tab)
        self._build_workflow_tab(workflow_tab)

        ttk.Separator(self).pack(fill="x", padx=12, pady=(8, 0))
        ttk.Label(self, textvariable=self.status, padding=(14, 9), anchor="w").pack(fill="x")

    def _build_mapping_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Reconcile Vault PDFs to the frozen source register, family Markdown and exact catalogue SKU rows.",
            wraplength=790,
        ).pack(anchor="w", pady=(0, 10))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.product_files).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse…", command=self._browse).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=10)
        self.preview_button = ttk.Button(actions, text="Validate & preview", command=self._preview)
        self.preview_button.pack(side="left")
        self.generate_button = ttk.Button(
            actions,
            text="Generate private family pages…",
            command=self._generate,
            state="disabled",
        )
        self.generate_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open local reports", command=self._open_reports).pack(side="left", padx=(8, 0))

        self.results = tk.Text(parent, wrap="word", height=20, state="disabled", font=("Consolas", 10))
        self.results.pack(fill="both", expand=True)
        self._show_results(
            "Select the local product_files folder, then run validation.\n"
            "The check hashes each PDF again, validates its existing readability record, "
            "and matches family IDs only through the frozen register."
        )

    def _build_workflow_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Explicit local actions; commands are fixed and never run through a shell.").pack(
            anchor="w", pady=(0, 12)
        )
        ttk.Button(parent, text="Run focused local tests", command=self._run_tests).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "No arbitrary command runner, automatic product activation, or cloud/LLM workflow is enabled. "
                "Family assignments with no hash-backed register link remain unassigned."
            ),
            wraplength=790,
        ).pack(anchor="w", pady=(16, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose local product_files folder",
            initialdir=self.product_files.get() or str(Path.home() / "Desktop"),
        )
        if selected:
            self.product_files.set(selected)
            self.current_report = None
            self.generate_button.configure(state="disabled")

    def _preview(self) -> None:
        selected = Path(self.product_files.get().strip())
        if not selected.is_dir():
            messagebox.showerror("Product files not found", "Choose the local folder containing the product-file manifest.")
            return
        self.current_report = None
        self._begin("Checking PDF hashes and family/SKU links…")

        def work() -> None:
            try:
                report = build_reconciliation(selected, ROOT)
                self.events.put(("preview", report))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _generate(self) -> None:
        if self.current_report is None:
            return
        selected = Path(self.product_files.get().strip()).resolve()
        if str(selected) != self.current_report["product_files_root"]:
            self.current_report = None
            self.generate_button.configure(state="disabled")
            messagebox.showerror("Preview required", "Run Validate & preview again for the selected folder.")
            return
        if self.current_report["validation_errors"]:
            messagebox.showerror("Validation required", "Fix the listed hash/readability issues before generating links.")
            return
        if not messagebox.askyesno(
            "Write private local reports",
            f"Generate the family Markdown pages and index under:\n{LOCAL_OUTPUT}\n\n"
            "This does not modify source PDFs, catalogue data, or generated deployment literature.",
        ):
            return
        self._begin("Writing private local family pages…")

        def work() -> None:
            try:
                report = build_reconciliation(selected, ROOT)
                written = write_reconciliation(report, LOCAL_OUTPUT)
                self.events.put(("written", (report, written)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _run_tests(self) -> None:
        if not messagebox.askyesno("Run local tests", "Run the focused local reconciliation and literature tests?"):
            return
        self._begin("Running focused tests…")

        def work() -> None:
            command = [
                sys.executable, "-m", "pytest",
                "tests/test_vault_product_files.py",
                "tests/test_family_literature.py",
                "-q",
            ]
            try:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                    shell=False,
                )
                self.events.put(("tests", (result.returncode, result.stdout, result.stderr)))
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _begin(self, message: str) -> None:
        self.status.set(message)
        self.preview_button.configure(state="disabled")
        self.generate_button.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "preview":
                    self.current_report = payload
                    self._display_report(payload)
                    self.preview_button.configure(state="normal")
                    can_write = not payload["validation_errors"]
                    self.generate_button.configure(state="normal" if can_write else "disabled")
                    self.status.set("Preview complete; no source files were changed.")
                elif event == "written":
                    report, written = payload
                    self.current_report = report
                    self._display_report(report)
                    self.preview_button.configure(state="normal")
                    self.generate_button.configure(state="normal")
                    self.status.set(f"Generated {len(written)} private report files under {LOCAL_OUTPUT}.")
                elif event == "tests":
                    code, stdout, stderr = payload
                    output = (stdout + ("\n" + stderr if stderr else "")).strip()
                    self._show_results(output or f"Test process exited with code {code}.")
                    self.preview_button.configure(state="normal")
                    self.generate_button.configure(state="normal" if self.current_report else "disabled")
                    self.status.set("Focused tests passed." if code == 0 else f"Focused tests failed (exit {code}).")
                elif event == "error":
                    self.preview_button.configure(state="normal")
                    self.generate_button.configure(state="normal" if self.current_report else "disabled")
                    self.status.set("Action failed; see error message.")
                    messagebox.showerror("Local action failed", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _display_report(self, report: dict) -> None:
        summary = report["summary"]
        lines = [
            "LOCAL RECONCILIATION",
            f"Product PDFs: {summary['pdf_count']} ({summary['unique_hash_count']} unique hashes)",
            f"Hash/readability errors: {summary['hash_validation_errors']}",
            f"Catalogue rows: {summary['catalogue_sku_rows']} across {summary['catalogue_families']} families",
            f"Family Markdown documents: {summary['family_markdown_count']}",
            f"PDF-linked families: {summary['mapped_family_count']}",
            f"PDFs without a family assignment: {summary['unassigned_pdf_count']}",
            "",
            "SKU coverage is shown in the private family pages. The generated public-facing family Markdown",
            "was corrected to include every source row; SKU duplicates remain separate and visible.",
            "Hash links do not approve document currency, SKU applicability, or product claims.",
        ]
        if report["validation_errors"]:
            lines.extend(["", "VALIDATION ERRORS", *[f"- {item}" for item in report["validation_errors"]]])
        if report["unassigned_files"]:
            lines.extend(["", "UNASSIGNED PDFS (not guessed)"])
            lines.extend(f"- {item['filename']}  [{item['sha256']}]" for item in report["unassigned_files"])
        if report["unmapped_register_families"]:
            lines.extend(["", "REGISTER FAMILY IDs WITHOUT MARKDOWN"])
            lines.extend(f"- {family}" for family in report["unmapped_register_families"])
        self._show_results("\n".join(lines))

    def _show_results(self, text: str) -> None:
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", text)
        self.results.configure(state="disabled")

    def _open_reports(self) -> None:
        if not LOCAL_OUTPUT.is_dir():
            messagebox.showinfo("No reports yet", "Generate the private local family pages first.")
            return
        if os.name == "nt":
            os.startfile(LOCAL_OUTPUT)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("Local reports", str(LOCAL_OUTPUT))


if __name__ == "__main__":
    AuroraManager().mainloop()
