"""
Funscript Forge — a workflow UI wrapper for funscript-tools.

Built on top of the funscript-tools processing engine by edger477:
  https://github.com/edger477/funscript-tools

This UI adds a guided 4-step workflow (Load → Configure → Review → Export)
with before/after waveform visualization so you can see what each transform
does before committing to output files.

All credit for the underlying algorithms, transforms, and processing pipeline
goes to edger477 and contributors. This wrapper simply provides an end-to-end
user experience around their work.
"""

import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

import matplotlib as mpl
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as FigureCanvas

plt.style.use(["ggplot", "dark_background", "fast"])

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ConfigManager
from funscript import Funscript
from processor import RestimProcessor
from ui.parameter_tabs import ParameterTabs

try:
    from tkinterdnd2 import DND_ALL, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

CREDIT = (
    "Processing engine by edger477\n"
    "https://github.com/edger477/funscript-tools\n\n"
    "This UI is a workflow wrapper — all credit for the\n"
    "algorithms and transforms belongs to edger477 and contributors."
)


class ForgeWindow:
    def __init__(self):
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("Funscript Forge")
        self.root.geometry("1150x820")
        self.root.minsize(900, 700)

        # State
        self.input_file: Optional[Path] = None
        self.source_funscript: Optional[Funscript] = None
        self.output_files: Dict[str, Path] = {}
        self.selected_outputs: Dict[str, tk.BooleanVar] = {}

        # Config
        self.config_manager = ConfigManager()
        self.current_config = self.config_manager.get_config()

        # Progress
        self.progress_var = tk.IntVar(value=0)
        self.status_var = tk.StringVar(value="Load a .funscript file to begin.")

        self._build_ui()

    # ─── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self._build_tab_input()
        self._build_tab_configure()
        self._build_tab_review()
        self._build_tab_export()
        self._build_status_bar()

        # Tabs 2-4 locked until file is loaded
        self.notebook.tab(1, state="disabled")
        self.notebook.tab(2, state="disabled")
        self.notebook.tab(3, state="disabled")

    # ── Tab 1: Input ──────────────────────────────────────────────────────────

    def _build_tab_input(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  1 · Input  ")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=3)
        tab.rowconfigure(0, weight=1)

        # Left panel
        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        # Credit banner
        credit_frame = ttk.LabelFrame(left, text="About")
        credit_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 5))
        credit_frame.columnconfigure(0, weight=1)
        ttk.Label(
            credit_frame,
            text="Processing engine by edger477",
            font=("", 9, "bold"),
            foreground="#4fc3f7",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 0))
        ttk.Label(
            credit_frame,
            text="github.com/edger477/funscript-tools",
            font=("", 8),
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 2))
        ttk.Label(
            credit_frame,
            text="This UI provides an end-to-end workflow\naround their algorithms and transforms.",
            font=("", 8),
            justify="left",
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 6))

        # Project / file load
        project_frame = ttk.LabelFrame(left, text="Project")
        project_frame.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 5))
        project_frame.columnconfigure(0, weight=1)

        self.drop_label = ttk.Label(
            project_frame,
            text="Drop .funscript here\nor click Browse",
            anchor="center",
            justify="center",
            relief="groove",
            padding=18,
        )
        self.drop_label.grid(row=0, column=0, sticky="ew", padx=8, pady=8)

        ttk.Button(project_frame, text="Browse...", command=self._browse_file).grid(
            row=1, column=0, sticky="ew", padx=8, pady=(0, 8)
        )

        # File info
        info_frame = ttk.LabelFrame(left, text="File Info")
        info_frame.grid(row=2, column=0, sticky="nsew", padx=0, pady=(0, 5))
        info_frame.columnconfigure(1, weight=1)

        self.lbl_filename = ttk.Label(info_frame, text="—", font=("", 9, "bold"))
        self.lbl_filename.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))

        for row_i, (label, attr) in enumerate(
            [("Actions:", "lbl_actions"), ("Duration:", "lbl_duration"), ("Range:", "lbl_range")],
            start=1,
        ):
            ttk.Label(info_frame, text=label).grid(row=row_i, column=0, sticky="w", padx=8, pady=1)
            lbl = ttk.Label(info_frame, text="—")
            lbl.grid(row=row_i, column=1, sticky="w", pady=1)
            setattr(self, attr, lbl)

        # Next button
        self.btn_next_1 = ttk.Button(
            left, text="Configure →", state="disabled",
            command=lambda: self.notebook.select(1)
        )
        self.btn_next_1.grid(row=3, column=0, sticky="ew", padx=0, pady=(0, 0))

        # Right: waveform
        right = ttk.LabelFrame(tab, text="Input Waveform")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.input_fig = Figure(tight_layout=True)
        self.input_mpl = FigureCanvas(self.input_fig, master=right)
        self.input_mpl.draw()
        self.input_mpl.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

        # DnD
        if HAS_DND:
            try:
                self.drop_label.drop_target_register(DND_ALL)
                self.drop_label.dnd_bind("<<Drop>>", self._handle_drop)
            except Exception:
                pass

    # ── Tab 2: Configure ──────────────────────────────────────────────────────

    def _build_tab_configure(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  2 · Configure  ")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=2)
        tab.rowconfigure(0, weight=1)
        tab.rowconfigure(1, weight=0)

        # ── Left: Creative sub-tab | Full Config sub-tab ──────────────────────
        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        left_nb = ttk.Notebook(left)
        left_nb.grid(row=0, column=0, sticky="nsew")
        self._left_nb = left_nb

        # ── Creative tab ──────────────────────────────────────────────────────
        creative_tab = ttk.Frame(left_nb)
        left_nb.add(creative_tab, text="  Creative  ")
        creative_tab.columnconfigure(0, weight=1)

        # Scrollable creative panel
        cc = tk.Canvas(creative_tab, highlightthickness=0)
        cc.pack(side="left", fill="both", expand=True)
        cc_sb = ttk.Scrollbar(creative_tab, orient="vertical", command=cc.yview)
        cc_sb.pack(side="right", fill="y")
        cc.configure(yscrollcommand=cc_sb.set)

        inner = ttk.Frame(cc)
        cc.create_window((0, 0), window=inner, anchor="nw")
        inner.columnconfigure(0, weight=1)
        inner.bind(
            "<Configure>",
            lambda e: cc.configure(scrollregion=cc.bbox("all"))
        )
        # Enable mousewheel scroll
        cc.bind("<Enter>", lambda e: cc.bind_all("<MouseWheel>",
            lambda ev: cc.yview_scroll(-1 * (ev.delta // 120), "units")))
        cc.bind("<Leave>", lambda e: cc.unbind_all("<MouseWheel>"))

        self._build_creative_panel(inner)

        # ── Full Config tab ───────────────────────────────────────────────────
        full_tab = ttk.Frame(left_nb)
        left_nb.add(full_tab, text="  Full Config  ")
        full_tab.columnconfigure(0, weight=1)
        full_tab.rowconfigure(0, weight=1)

        self.parameter_tabs = ParameterTabs(full_tab, self.current_config)
        self.parameter_tabs.grid(row=0, column=0, sticky="nsew")
        self.parameter_tabs.set_mode_change_callback(lambda m: None)
        self.parameter_tabs.set_conversion_callbacks(
            self._convert_basic_2d, self._convert_prostate_2d
        )

        # ── Right: Before / After preview ────────────────────────────────────
        right = ttk.LabelFrame(tab, text="Preview")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)

        before_frame = ttk.LabelFrame(right, text="Before (original)")
        before_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(5, 2))
        before_frame.columnconfigure(0, weight=1)
        before_frame.rowconfigure(0, weight=1)

        self.before_fig = Figure(tight_layout=True)
        self.before_mpl = FigureCanvas(self.before_fig, master=before_frame)
        self.before_mpl.draw()
        self.before_mpl.get_tk_widget().pack(fill="both", expand=True)

        # Output selector
        sel_row = ttk.Frame(right)
        sel_row.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(sel_row, text="Preview output:").pack(side="left", padx=(0, 5))
        self.preview_var = tk.StringVar(value="— process first —")
        self.preview_combo = ttk.Combobox(
            sel_row, textvariable=self.preview_var, state="readonly", width=22
        )
        self.preview_combo.pack(side="left")
        self.preview_combo.bind("<<ComboboxSelected>>", self._on_preview_selected)

        self.after_label_frame = ttk.LabelFrame(right, text="After")
        self.after_label_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=(2, 5))
        self.after_label_frame.columnconfigure(0, weight=1)
        self.after_label_frame.rowconfigure(0, weight=1)

        self.after_fig = Figure(tight_layout=True)
        self.after_mpl = FigureCanvas(self.after_fig, master=self.after_label_frame)
        self.after_mpl.draw()
        self.after_mpl.get_tk_widget().pack(fill="both", expand=True)

        # Bottom: nav + process
        btn_row = ttk.Frame(tab)
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Button(btn_row, text="← Back",
                   command=lambda: self.notebook.select(0)).pack(side="left", padx=5)
        self.btn_process = ttk.Button(
            btn_row, text="Process →", command=self._start_processing
        )
        self.btn_process.pack(side="right", padx=5)

    def _build_creative_panel(self, parent):
        """Build the simplified creative controls panel."""
        cfg = self.current_config
        row = 0

        def section(text):
            nonlocal row
            ttk.Separator(parent, orient="horizontal").grid(
                row=row, column=0, sticky="ew", padx=4, pady=(8, 2)
            )
            row += 1
            ttk.Label(parent, text=text, font=("", 9, "bold")).grid(
                row=row, column=0, sticky="w", padx=8, pady=(0, 4)
            )
            row += 1

        def labeled_row(label_text, widget_factory):
            nonlocal row
            f = ttk.Frame(parent)
            f.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
            f.columnconfigure(1, weight=1)
            ttk.Label(f, text=label_text, width=20, anchor="w").grid(row=0, column=0, sticky="w")
            w = widget_factory(f)
            w.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            row += 1
            return w

        ttk.Label(parent, text="Key parameters that shape how the output feels.\nAdjust → Process → compare before/after.",
                  font=("", 8), justify="left", foreground="#aaaaaa"
                  ).grid(row=row, column=0, sticky="w", padx=8, pady=(8, 0))
        row += 1

        # ── Motion Axis ───────────────────────────────────────────────────────
        section("Motion Axis — 2D path on electrode")

        ab = cfg.get("alpha_beta_generation", {})

        self.cv_algo = tk.StringVar(value=ab.get("algorithm", "top-right-left"))
        labeled_row("Algorithm", lambda p: ttk.Combobox(
            p, textvariable=self.cv_algo, state="readonly",
            values=["circular", "top-right-left", "top-left-right", "restim-original"],
            width=18,
        ))

        self.cv_pps = tk.IntVar(value=ab.get("points_per_second", 25))
        labeled_row("Points / second", lambda p: ttk.Spinbox(
            p, from_=1, to=100, textvariable=self.cv_pps, width=6
        ))

        self.cv_min_dist = tk.DoubleVar(value=ab.get("min_distance_from_center", 0.1))
        labeled_row("Min dist. from center", lambda p: ttk.Scale(
            p, from_=0.05, to=0.9, variable=self.cv_min_dist, orient="horizontal"
        ))

        self.cv_speed_thresh = tk.IntVar(value=ab.get("speed_threshold_percent", 50))
        labeled_row("Speed threshold %", lambda p: ttk.Spinbox(
            p, from_=0, to=100, textvariable=self.cv_speed_thresh, width=6
        ))

        # ── Prostate ──────────────────────────────────────────────────────────
        section("Prostate 2D")

        pg = cfg.get("prostate_generation", {})
        self.cv_prostate_en = tk.BooleanVar(value=pg.get("generate_prostate_files", True))
        f_pr = ttk.Frame(parent)
        f_pr.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row += 1
        ttk.Checkbutton(f_pr, text="Generate prostate files", variable=self.cv_prostate_en).pack(anchor="w")

        self.cv_prostate_algo = tk.StringVar(value=pg.get("algorithm", "tear-shaped"))
        labeled_row("Algorithm", lambda p: ttk.Combobox(
            p, textvariable=self.cv_prostate_algo, state="readonly",
            values=["tear-shaped", "circular"],
            width=14,
        ))

        # ── Frequency ─────────────────────────────────────────────────────────
        section("Frequency — pulse rate")

        fq = cfg.get("frequency", {})

        self.cv_freq_ramp_ratio = tk.DoubleVar(value=fq.get("frequency_ramp_combine_ratio", 2.0))
        labeled_row("Ramp : Speed blend", lambda p: ttk.Scale(
            p, from_=1.0, to=10.0, variable=self.cv_freq_ramp_ratio, orient="horizontal"
        ))

        self.cv_pulse_freq_ratio = tk.DoubleVar(value=fq.get("pulse_frequency_combine_ratio", 3.0))
        labeled_row("Pulse freq blend", lambda p: ttk.Scale(
            p, from_=1.0, to=10.0, variable=self.cv_pulse_freq_ratio, orient="horizontal"
        ))

        self.cv_pf_min = tk.DoubleVar(value=fq.get("pulse_freq_min", 0.40))
        labeled_row("Pulse freq min", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pf_min, orient="horizontal"
        ))

        self.cv_pf_max = tk.DoubleVar(value=fq.get("pulse_freq_max", 0.95))
        labeled_row("Pulse freq max", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pf_max, orient="horizontal"
        ))

        # ── Pulse Shape ───────────────────────────────────────────────────────
        section("Pulse Shape — feel of each pulse")

        pu = cfg.get("pulse", {})

        self.cv_pw_min = tk.DoubleVar(value=pu.get("pulse_width_min", 0.1))
        labeled_row("Width min", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pw_min, orient="horizontal"
        ))

        self.cv_pw_max = tk.DoubleVar(value=pu.get("pulse_width_max", 0.45))
        labeled_row("Width max", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pw_max, orient="horizontal"
        ))

        self.cv_pr_min = tk.DoubleVar(value=pu.get("pulse_rise_min", 0.0))
        labeled_row("Rise time min", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pr_min, orient="horizontal"
        ))

        self.cv_pr_max = tk.DoubleVar(value=pu.get("pulse_rise_max", 0.80))
        labeled_row("Rise time max", lambda p: ttk.Scale(
            p, from_=0.0, to=1.0, variable=self.cv_pr_max, orient="horizontal"
        ))

        # ── Output mode ───────────────────────────────────────────────────────
        section("Output Mode")

        ax = cfg.get("positional_axes", {})
        self.cv_gen_3p = tk.BooleanVar(value=ax.get("generate_legacy", True))
        self.cv_gen_4p = tk.BooleanVar(value=ax.get("generate_motion_axis", True))

        f_mode = ttk.Frame(parent)
        f_mode.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row += 1
        ttk.Checkbutton(f_mode, text="Generate 3P (alpha/beta)", variable=self.cv_gen_3p).pack(anchor="w")
        ttk.Checkbutton(f_mode, text="Generate 4P (E1–E4)", variable=self.cv_gen_4p).pack(anchor="w")

        # Spacer
        ttk.Frame(parent).grid(row=row, column=0, pady=10)

    def _collect_creative_config(self):
        """Push creative panel values into current_config before processing."""
        cfg = self.current_config

        cfg["alpha_beta_generation"]["algorithm"] = self.cv_algo.get()
        cfg["alpha_beta_generation"]["points_per_second"] = self.cv_pps.get()
        cfg["alpha_beta_generation"]["min_distance_from_center"] = round(self.cv_min_dist.get(), 3)
        cfg["alpha_beta_generation"]["speed_threshold_percent"] = self.cv_speed_thresh.get()

        cfg["prostate_generation"]["generate_prostate_files"] = self.cv_prostate_en.get()
        cfg["prostate_generation"]["algorithm"] = self.cv_prostate_algo.get()

        cfg["frequency"]["frequency_ramp_combine_ratio"] = round(self.cv_freq_ramp_ratio.get(), 1)
        cfg["frequency"]["pulse_frequency_combine_ratio"] = round(self.cv_pulse_freq_ratio.get(), 1)
        cfg["frequency"]["pulse_freq_min"] = round(self.cv_pf_min.get(), 3)
        cfg["frequency"]["pulse_freq_max"] = round(self.cv_pf_max.get(), 3)

        cfg["pulse"]["pulse_width_min"] = round(self.cv_pw_min.get(), 3)
        cfg["pulse"]["pulse_width_max"] = round(self.cv_pw_max.get(), 3)
        cfg["pulse"]["pulse_rise_min"] = round(self.cv_pr_min.get(), 3)
        cfg["pulse"]["pulse_rise_max"] = round(self.cv_pr_max.get(), 3)

        cfg["positional_axes"]["generate_legacy"] = self.cv_gen_3p.get()
        cfg["positional_axes"]["generate_motion_axis"] = self.cv_gen_4p.get()

    def _on_preview_selected(self, event=None):
        suffix = self.preview_var.get()
        if suffix and suffix in self.output_files:
            self._update_after_preview(suffix)

    def _update_after_preview(self, suffix: str):
        if not self.source_funscript:
            return
        try:
            fs = Funscript.from_file(self.output_files[suffix])
            self.after_label_frame.config(text=f"After — {suffix}")
            self._plot_comparison(
                self.after_fig, self.after_mpl,
                self.source_funscript, fs, suffix
            )
        except Exception as e:
            self._set_status(0, f"Preview error: {e}")

    # ── Tab 3: Review ─────────────────────────────────────────────────────────

    def _build_tab_review(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  3 · Review  ")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=3)
        tab.rowconfigure(0, weight=1)
        tab.rowconfigure(1, weight=0)

        # Left: output checklist
        left = ttk.LabelFrame(tab, text="Generated Outputs")
        left.grid(row=0, column=0, sticky="nsew", padx=(5, 2), pady=5)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        # Scrollable list
        list_canvas = tk.Canvas(left, highlightthickness=0)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=list_canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        list_canvas.configure(yscrollcommand=scrollbar.set)

        self.output_list_frame = ttk.Frame(list_canvas)
        list_canvas.create_window((0, 0), window=self.output_list_frame, anchor="nw")
        self.output_list_frame.bind(
            "<Configure>",
            lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all"))
        )

        ttk.Label(self.output_list_frame, text="Process first to see outputs.").pack(padx=8, pady=8)

        # Right: comparison plots
        right = ttk.LabelFrame(tab, text="Comparison")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 5), pady=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        top_plot = ttk.LabelFrame(right, text="Original")
        top_plot.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 2))
        top_plot.columnconfigure(0, weight=1)
        top_plot.rowconfigure(0, weight=1)

        self.review_before_fig = Figure(tight_layout=True)
        self.review_before_mpl = FigureCanvas(self.review_before_fig, master=top_plot)
        self.review_before_mpl.draw()
        self.review_before_mpl.get_tk_widget().pack(fill="both", expand=True)

        self.review_after_lf = ttk.LabelFrame(right, text="Selected Output")
        self.review_after_lf.grid(row=1, column=0, sticky="nsew", padx=5, pady=(2, 5))
        self.review_after_lf.columnconfigure(0, weight=1)
        self.review_after_lf.rowconfigure(0, weight=1)

        self.review_after_fig = Figure(tight_layout=True)
        self.review_after_mpl = FigureCanvas(self.review_after_fig, master=self.review_after_lf)
        self.review_after_mpl.draw()
        self.review_after_mpl.get_tk_widget().pack(fill="both", expand=True)

        # Bottom nav
        btn_row = ttk.Frame(tab)
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Button(btn_row, text="← Back",
                   command=lambda: self.notebook.select(1)).pack(side="left", padx=5)
        ttk.Button(btn_row, text="Export →",
                   command=lambda: self.notebook.select(3)).pack(side="right", padx=5)

    # ── Tab 4: Export ─────────────────────────────────────────────────────────

    def _build_tab_export(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  4 · Export  ")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=0)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(2, weight=0)

        # Output directory
        dir_frame = ttk.LabelFrame(tab, text="Output Directory")
        dir_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        dir_frame.columnconfigure(1, weight=1)

        self.output_dir_var = tk.StringVar()
        ttk.Label(dir_frame, text="Save to:").grid(row=0, column=0, padx=8, pady=6)
        ttk.Entry(dir_frame, textvariable=self.output_dir_var).grid(
            row=0, column=1, sticky="ew", padx=5, pady=6
        )
        ttk.Button(dir_frame, text="Browse...", command=self._browse_output_dir).grid(
            row=0, column=2, padx=8, pady=6
        )

        # Files
        files_frame = ttk.LabelFrame(tab, text="Files to Export")
        files_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        files_frame.columnconfigure(0, weight=1)
        files_frame.rowconfigure(0, weight=1)

        self.export_list_frame = ttk.Frame(files_frame)
        self.export_list_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        ttk.Label(self.export_list_frame, text="No outputs generated yet.").pack()

        # Actions
        action_frame = ttk.Frame(tab)
        action_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=10)
        action_frame.columnconfigure(0, weight=1)

        ttk.Button(action_frame, text="← Back",
                   command=lambda: self.notebook.select(2)).pack(side="left", padx=5)

        self.lbl_export_status = ttk.Label(action_frame, text="", foreground="#4fc3f7")
        self.lbl_export_status.pack(side="left", padx=15)

        self.btn_new_project = ttk.Button(
            action_frame, text="New Project", state="disabled", command=self._new_project
        )
        self.btn_new_project.pack(side="right", padx=5)

        self.btn_open_folder = ttk.Button(
            action_frame, text="Open Folder", state="disabled", command=self._open_output_folder
        )
        self.btn_open_folder.pack(side="right", padx=5)

        self.btn_export = ttk.Button(
            action_frame, text="Export Selected Files", state="disabled",
            command=self._export_files
        )
        self.btn_export.pack(side="right", padx=10)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        bar = ttk.Frame(self.root, relief="sunken")
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(bar, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=(3, 1))

        ttk.Label(bar, textvariable=self.status_var, anchor="w").grid(
            row=1, column=0, sticky="ew", padx=8, pady=(0, 3)
        )

    # ─── File Loading ─────────────────────────────────────────────────────────

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select Funscript File",
            filetypes=[("Funscript files", "*.funscript"), ("All files", "*.*")],
        )
        if path:
            self._load_file(Path(path))

    def _handle_drop(self, event):
        data = event.data.strip()
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        path = Path(data)
        if path.suffix.lower() == ".funscript" and path.exists():
            self._load_file(path)

    def _load_file(self, path: Path):
        self._set_status(10, f"Loading {path.name}...")

        def _do():
            try:
                fs = Funscript.from_file(path)
                self.root.after(0, lambda: self._on_file_loaded(path, fs))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(0, f"Failed to load: {e}"))

        threading.Thread(target=_do, daemon=True).start()

    def _on_file_loaded(self, path: Path, fs: Funscript):
        self.input_file = path
        self.source_funscript = fs

        self.lbl_filename.config(text=path.name)
        self.lbl_actions.config(text=str(len(fs.x)))

        duration_s = float(fs.x[-1]) if len(fs.x) > 0 else 0
        m, s = int(duration_s // 60), int(duration_s % 60)
        self.lbl_duration.config(text=f"{m:02d}:{s:02d}")

        y_pct = fs.y * 100
        self.lbl_range.config(text=f"{int(y_pct.min())} – {int(y_pct.max())}")

        self.output_dir_var.set(str(path.parent))

        # Plots
        self._plot_funscript(self.input_fig, self.input_mpl, fs, "Input")
        self._plot_funscript(self.before_fig, self.before_mpl, fs, "Original")
        self._plot_funscript(self.review_before_fig, self.review_before_mpl, fs, "Original")

        self.drop_label.config(text=path.name)
        self.notebook.tab(1, state="normal")
        self.btn_next_1.config(state="normal")
        self._set_status(100, f"Loaded {path.name} — {len(fs.x)} actions, {m:02d}:{s:02d}")

    # ─── Visualization ────────────────────────────────────────────────────────

    def _plot_funscript(self, fig: Figure, canvas: FigureCanvas, fs: Funscript, label: str):
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(fs.x, fs.y * 100, linewidth=0.7, color="#4fc3f7", label=label)
        ax.set_ylim(0, 100)
        ax.set_xlabel("Time (s)", fontsize=8)
        ax.set_ylabel("Position", fontsize=8)
        ax.tick_params(labelsize=7)
        fig.tight_layout()
        canvas.draw()

    def _plot_comparison(
        self,
        fig: Figure,
        canvas: FigureCanvas,
        original: Funscript,
        processed: Funscript,
        label: str,
    ):
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(original.x, original.y * 100, linewidth=0.5,
                color="#555555", alpha=0.6, label="original")
        ax.plot(processed.x, processed.y * 100, linewidth=0.8,
                color="#4fc3f7", label=label)
        ax.set_ylim(0, 100)
        ax.legend(fontsize=7)
        ax.set_xlabel("Time (s)", fontsize=8)
        ax.tick_params(labelsize=7)
        fig.tight_layout()
        canvas.draw()

    # ─── Processing ───────────────────────────────────────────────────────────

    def _start_processing(self):
        if not self.input_file:
            return
        self.btn_process.config(state="disabled")
        # Collect from whichever panel is active
        self._collect_creative_config()
        self.parameter_tabs.update_config(self.current_config)
        self._set_status(0, "Processing...")
        threading.Thread(target=self._run_processor, daemon=True).start()

    def _run_processor(self):
        try:
            processor = RestimProcessor(self.current_config)
            success = processor.process(str(self.input_file), self._progress_callback)

            if success:
                custom = self.current_config.get("advanced", {}).get(
                    "custom_output_directory", ""
                ).strip()
                output_dir = Path(custom) if custom else self.input_file.parent
                stem = self.input_file.stem

                outputs = {}
                for p in output_dir.glob(f"{stem}.*.funscript"):
                    suffix = p.name[len(stem) + 1: -len(".funscript")]
                    outputs[suffix] = p

                self.output_files = outputs
                self.root.after(0, self._on_processing_done)
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: self._set_status(0, f"Processing error: {msg}"))
            self.root.after(0, lambda: self.btn_process.config(state="normal"))

    def _progress_callback(self, percent: int, message: str):
        self.root.after(0, lambda: self._set_status(percent, message))

    def _on_processing_done(self):
        self.btn_process.config(state="normal")
        n = len(self.output_files)
        self._set_status(100, f"Done — {n} file(s) generated")

        # Populate preview dropdown
        sorted_suffixes = sorted(self.output_files.keys())
        self.preview_combo["values"] = sorted_suffixes

        # Auto-select alpha if present, otherwise first output
        default = "alpha" if "alpha" in self.output_files else (sorted_suffixes[0] if sorted_suffixes else None)
        if default:
            self.preview_var.set(default)
            self._update_after_preview(default)

        self._populate_review()
        self._populate_export()

        self.notebook.tab(2, state="normal")
        self.notebook.tab(3, state="normal")
        self.notebook.select(2)

    # ─── 2D conversion pass-throughs (used by ParameterTabs buttons) ──────────

    def _convert_basic_2d(self):
        if not self.input_file:
            messagebox.showerror("Error", "Load a file first.")
            return
        self._start_processing()

    def _convert_prostate_2d(self):
        if not self.input_file:
            messagebox.showerror("Error", "Load a file first.")
            return
        self._start_processing()

    # ─── Review ───────────────────────────────────────────────────────────────

    def _populate_review(self):
        for w in self.output_list_frame.winfo_children():
            w.destroy()

        self.selected_outputs = {}

        if not self.output_files:
            ttk.Label(self.output_list_frame, text="No outputs.").pack(padx=8, pady=8)
            return

        ttk.Label(
            self.output_list_frame,
            text="Check to include in export.\nClick name to preview.",
            font=("", 8),
            justify="left",
        ).pack(anchor="w", padx=8, pady=(8, 4))

        ttk.Separator(self.output_list_frame, orient="horizontal").pack(
            fill="x", padx=4, pady=4
        )

        for suffix, path in sorted(self.output_files.items()):
            var = tk.BooleanVar(value=True)
            self.selected_outputs[suffix] = var

            row = ttk.Frame(self.output_list_frame)
            row.pack(fill="x", padx=4, pady=1)

            ttk.Checkbutton(row, variable=var).pack(side="left")
            ttk.Button(
                row, text=suffix, width=24,
                command=lambda s=suffix, p=path: self._preview_output(s, p),
            ).pack(side="left", padx=2)

        # Auto-preview first
        first_suffix, first_path = next(iter(self.output_files.items()))
        self._preview_output(first_suffix, first_path)

    def _preview_output(self, suffix: str, path: Path):
        if not self.source_funscript:
            return
        try:
            fs = Funscript.from_file(path)
            self.review_after_lf.config(text=f"Output: {suffix}")
            self._plot_comparison(
                self.review_after_fig, self.review_after_mpl,
                self.source_funscript, fs, suffix
            )
        except Exception as e:
            self._set_status(0, f"Preview error: {e}")

    # ─── Export ───────────────────────────────────────────────────────────────

    def _populate_export(self):
        for w in self.export_list_frame.winfo_children():
            w.destroy()

        if not self.output_files:
            ttk.Label(self.export_list_frame, text="No outputs generated yet.").pack()
            return

        ttk.Label(
            self.export_list_frame,
            text="Files are already saved to the source directory.\nCheck files to copy to a different output directory.",
            font=("", 8),
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        for suffix, path in sorted(self.output_files.items()):
            var = self.selected_outputs.get(suffix, tk.BooleanVar(value=True))
            ttk.Checkbutton(
                self.export_list_frame, variable=var, text=path.name
            ).pack(anchor="w", pady=1)

        self.btn_export.config(state="normal")

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Select Output Directory")
        if d:
            self.output_dir_var.set(d)

    def _export_files(self):
        output_dir = Path(self.output_dir_var.get())
        if not output_dir.exists():
            messagebox.showerror("Error", f"Directory does not exist:\n{output_dir}")
            return

        selected = [s for s, var in self.selected_outputs.items() if var.get()]
        if not selected:
            messagebox.showwarning("Nothing selected", "Select at least one file to export.")
            return

        count = 0
        for suffix in selected:
            src = self.output_files.get(suffix)
            if src and src.exists():
                dst = output_dir / src.name
                if src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
                count += 1

        self.lbl_export_status.config(text=f"{count} file(s) exported")
        self.btn_open_folder.config(state="normal")
        self.btn_new_project.config(state="normal")
        self._set_status(100, f"Done — {count} file(s) exported to {output_dir}")

    def _open_output_folder(self):
        d = self.output_dir_var.get()
        if d:
            subprocess.Popen(f'explorer "{d}"')

    def _new_project(self):
        self.input_file = None
        self.source_funscript = None
        self.output_files = {}
        self.selected_outputs = {}

        self.lbl_filename.config(text="—")
        self.lbl_actions.config(text="—")
        self.lbl_duration.config(text="—")
        self.lbl_range.config(text="—")
        self.drop_label.config(text="Drop .funscript here\nor click Browse")
        self.lbl_export_status.config(text="")
        self.preview_var.set("— process first —")
        self.preview_combo["values"] = []

        for fig, canvas in [
            (self.input_fig, self.input_mpl),
            (self.before_fig, self.before_mpl),
            (self.after_fig, self.after_mpl),
            (self.review_before_fig, self.review_before_mpl),
            (self.review_after_fig, self.review_after_mpl),
        ]:
            fig.clear()
            canvas.draw()

        self.notebook.tab(1, state="disabled")
        self.notebook.tab(2, state="disabled")
        self.notebook.tab(3, state="disabled")
        self.btn_next_1.config(state="disabled")
        self.btn_export.config(state="disabled")
        self.btn_open_folder.config(state="disabled")
        self.btn_new_project.config(state="disabled")
        self.notebook.select(0)
        self._set_status(0, "Load a .funscript file to begin.")

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _set_status(self, percent: int, message: str):
        self.status_var.set(message)
        self.progress_var.set(max(0, percent))

    def run(self):
        self.root.mainloop()


def main():
    app = ForgeWindow()
    app.run()


if __name__ == "__main__":
    main()
