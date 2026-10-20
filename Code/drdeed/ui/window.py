"""Tkinter user interface for the local legal-text-to-DXF workflow."""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..application.parsing import (
    LlmSurveyParser,
    ParsingRecoveryService,
    SurveyParsingService,
    SystemSurveyPrompter,
)
from ..application.service import SurveyProcessingApplicationService
from ..domain.models import CadExportConfig, Point2D, SurveyProcessingResult
from ..geometry.calculator import StandardTraverseCalculator
from ..geometry.validation import SurveyClosureValidator
from ..infrastructure.cad.export import CadExportService
from ..infrastructure.llm.ollama_client import OllamaChatClient


class SurveyProcessingWindow: #general UI
    def __init__(
        self,
        root: tk.Tk,
        application_service: SurveyProcessingApplicationService,
    ) -> None:
        self._root = root
        self._application_service = application_service
        self._results: queue.Queue[SurveyProcessingResult | Exception] = queue.Queue()

        root.title("DrDeed - Legal Description to DXF") #window title
        root.geometry("900x760")
        root.minsize(700, 600)

        container = ttk.Frame(root, padding=12) #styling
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(6, weight=1)

        ttk.Label(
            container,
            text="Paste legal-description text (OCR is not included).", #textbox label
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W)
        self._source_text = tk.Text(container, height=12, wrap=tk.WORD) #textbox
        self._source_text.grid( #textbox styling
            row=1,
            column=0,
            columnspan=3,
            sticky=tk.NSEW,
            pady=(4, 12),
        )

        self._easting = self._add_entry(container, 2, "POB easting:", "0") #inputs for starting coords and min precisions
        self._northing = self._add_entry(container, 3, "POB northing:", "0")
        self._threshold = self._add_entry(
            container,
            4,
            "Minimum precision denominator:",
            "5000",
        )

        ttk.Label(container, text="DXF output:").grid( #label for output path
            row=5,
            column=0,
            sticky=tk.W,
            pady=(4, 0),
        )
        self._output_path = tk.StringVar(value=str(Path.cwd() / "traverse.dxf")) #texbox
        ttk.Entry(container, textvariable=self._output_path).grid(
            row=5,
            column=1,
            sticky=tk.EW,
            pady=(4, 0),
        )
        ttk.Button(container, text="Browse...", command=self._choose_output).grid( #look for file path
            row=5,
            column=2,
            padx=(8, 0),
            pady=(4, 0),
        )

        self._run_button = ttk.Button( #go to the orchestrator
            container,
            text="Parse, Check, and Export DXF",
            command=self._start_processing,
        )
        self._run_button.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(12, 4),
        )

        self._status = tk.StringVar(value="Ready. Local Ollama must be running.") #status message
        ttk.Label(container, textvariable=self._status, wraplength=850).grid(
            row=7,
            column=0,
            columnspan=3,
            sticky=tk.W,
            pady=(0, 6),
        )
        self._results_text = tk.Text(container, height=12, wrap=tk.WORD, state=tk.DISABLED) #results (text)
        self._results_text.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky=tk.NSEW,
        )
        container.rowconfigure(8, weight=1)

    @staticmethod
    def _add_entry(
        parent: ttk.Frame,
        row: int,
        label: str,
        initial_value: str,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
        entry = ttk.Entry(parent)
        entry.insert(0, initial_value)
        entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW, pady=3)
        return entry

    def _choose_output(self) -> None:
        chosen = filedialog.asksaveasfilename(
            title="Save traverse DXF",
            defaultextension=".dxf",
            filetypes=[("DXF drawing", "*.dxf")],
            initialfile=Path(self._output_path.get()).name,
        )
        if chosen:
            self._output_path.set(chosen)

    def _start_processing(self) -> None: #send stuff to the orchestrator
        raw_text = self._source_text.get("1.0", tk.END).strip()
        output_path = self._output_path.get().strip()
        if not raw_text:
            messagebox.showerror("Missing legal text", "Paste legal-description text first.")
            return
        if not output_path:
            messagebox.showerror("Missing output path", "Choose a DXF output path.")
            return

        try:
            pob = Point2D(
                easting=float(self._easting.get()),
                northing=float(self._northing.get()),
            )
            threshold = float(self._threshold.get())
            config = CadExportConfig(Path(output_path))
        except ValueError as error:
            messagebox.showerror("Invalid input", str(error))
            return

        self._run_button.configure(state=tk.DISABLED)
        self._status.set("Sending legal text to local Qwen3 through Ollama...")
        worker = threading.Thread(
            target=self._process_in_background,
            args=(raw_text, pob, threshold, config),
            daemon=True,
        )
        worker.start()
        self._root.after(100, self._poll_results)

    def _process_in_background( 
        self,
        raw_text: str,
        pob: Point2D,
        threshold: float,
        config: CadExportConfig,
    ) -> None:
        try:
            result = self._application_service.process_survey_text(
                raw_text,
                pob,
                threshold,
                config,
            )
        except Exception as error:
            self._results.put(error)
        else:
            self._results.put(result)

    def _poll_results(self) -> None:
        try:
            result = self._results.get_nowait()
        except queue.Empty:
            self._root.after(100, self._poll_results)
            return

        self._run_button.configure(state=tk.NORMAL)
        if isinstance(result, Exception):
            self._status.set("Processing failed.")
            messagebox.showerror("Survey processing failed", str(result))
            return

        self._show_result(result)

    def _show_result(self, result: SurveyProcessingResult) -> None: #show final results
        report = result.closure_report
        lines = [
            f"Point of beginning: {result.traverse.point_of_beginning_desc or '(not stated)'}",
            f"Parsed calls: {len(result.traverse.calls)}",
            f"Total perimeter: {report.total_perimeter:g}",
            f"Closure error: {report.closure_error_distance:g}",
            f"Precision ratio: 1:{report.precision_ratio:g}",
            f"Meets requested threshold: {'yes' if report.is_acceptable() else 'no'}",
            f"Correction attempts: {result.correction_attempts}",
            "",
        ]
        for call in result.traverse.calls:
            if call.is_curve():
                description = "curve data retained; curve geometry not supported yet"
            elif call.bearing is None or call.distance is None:
                description = "line call is missing a bearing or distance"
            else:
                description = (
                    f"{call.bearing.to_quadrant_text()} / {call.distance.value:g}"
                )
            lines.append(f"{call.sequence_index}. {description} — {call.raw_text}")

        if result.output_file_path is None:
            lines.extend(
                [
                    "",
                    "No DXF was exported because closure did not meet the requested threshold.",
                    "Review the source, parsed calls, and firm-specific acceptance criteria.",
                ]
            )
            self._status.set("Review required: closure threshold was not met; no DXF written.")
        else:
            lines.extend(["", f"DXF created: {result.output_file_path}"])
            self._status.set("Processing complete.")

        self._results_text.configure(state=tk.NORMAL)
        self._results_text.delete("1.0", tk.END)
        self._results_text.insert("1.0", "\n".join(lines))
        self._results_text.configure(state=tk.DISABLED)


def create_application_service(
    model_name: str = "qwen3:8b",
) -> SurveyProcessingApplicationService:
    prompter = SystemSurveyPrompter()
    parser = LlmSurveyParser(OllamaChatClient(model_name), prompter)
    recovery = ParsingRecoveryService(parser, prompter)
    return SurveyProcessingApplicationService(
        parsing_service=SurveyParsingService(parser, recovery),
        calculator=StandardTraverseCalculator(),
        validation_service=SurveyClosureValidator(),
        export_service=CadExportService(),
    )


def run_ui(model_name: str = "qwen3:8b") -> None: #startup function
    root = tk.Tk()
    SurveyProcessingWindow(root, create_application_service(model_name))
    root.mainloop()
