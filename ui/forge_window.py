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
from cli import get_default_config, list_outputs, load_file, process
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
        self.source_data: Optional[dict] = None   # dict from cli.load_file
        self.output_files: Dict[str, Path] = {}
        self.selected_outputs: Dict[str, tk.BooleanVar] = {}

        # Config — plain dict, no upstream objects
        self.current_config = get_default_config()

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

        self.parameter_tabs = ParameterTabs(full_tab, self.current_config)  # our UI widget, not upstream
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

    # ── Algorithm metadata ─────────────────────────────────────────────────────

    _ALGO_INFO = {
        "circular": {
            "label": "Circular arc  (0° – 180°)",
            "hint": "Smooth semi-circle. Balanced — works well for most content.",
        },
        "top-right-left": {
            "label": "Wide arc  (0° – 270°)",
            "hint": "Larger sweep. More contrast between strokes — good for energetic content.",
        },
        "top-left-right": {
            "label": "Narrow arc  (0° – 90°)",
            "hint": "Subtle movement. Works well for slow, building content.",
        },
        "restim-original": {
            "label": "Full circle with reversals  (0° – 360°)",
            "hint": "Most unpredictable. Random direction changes — maximally varied.",
        },
    }

    def _build_creative_panel(self, parent):
        """Guided creative controls — each knob explains what you will feel."""
        cfg = self.current_config
        row = 0

        # ── helpers ───────────────────────────────────────────────────────────

        def section(title, subtitle):
            nonlocal row
            ttk.Separator(parent, orient="horizontal").grid(
                row=row, column=0, sticky="ew", padx=4, pady=(10, 2))
            row += 1
            ttk.Label(parent, text=title, font=("", 9, "bold")).grid(
                row=row, column=0, sticky="w", padx=8, pady=(0, 0))
            row += 1
            ttk.Label(parent, text=subtitle, font=("", 8), foreground="#888888",
                      justify="left", wraplength=300).grid(
                row=row, column=0, sticky="w", padx=8, pady=(0, 4))
            row += 1

        def guided_slider(label, hint, var, from_, to_, on_change=None):
            """Slider + live value label + hint text below."""
            nonlocal row
            # Label row
            hdr = ttk.Frame(parent)
            hdr.grid(row=row, column=0, sticky="ew", padx=8, pady=(4, 0))
            hdr.columnconfigure(0, weight=1)
            ttk.Label(hdr, text=label, font=("", 8, "bold"), anchor="w").grid(
                row=0, column=0, sticky="w")
            val_lbl = ttk.Label(hdr, text=f"{var.get():.2f}", font=("", 8),
                                foreground="#4fc3f7", width=6, anchor="e")
            val_lbl.grid(row=0, column=1, sticky="e")
            row += 1
            # Slider
            def _on_slide(v, _var=var, _lbl=val_lbl, _cb=on_change):
                _lbl.config(text=f"{float(v):.2f}")
                if _cb:
                    _cb()
                self._schedule_sensation_update()
            sl = ttk.Scale(parent, from_=from_, to=to_, variable=var, orient="horizontal",
                           command=_on_slide)
            sl.grid(row=row, column=0, sticky="ew", padx=8, pady=(0, 1))
            row += 1
            # Hint
            ttk.Label(parent, text=hint, font=("", 7), foreground="#666666",
                      justify="left", wraplength=300).grid(
                row=row, column=0, sticky="w", padx=12, pady=(0, 2))
            row += 1
            return sl

        # ── What you'll feel — live summary ───────────────────────────────────
        summary_frame = ttk.LabelFrame(parent, text="What you'll feel")
        summary_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(8, 4))
        summary_frame.columnconfigure(0, weight=1)
        row += 1
        self._sensation_var = tk.StringVar(value="Adjust settings to see a description.")
        ttk.Label(summary_frame, textvariable=self._sensation_var,
                  font=("", 8), justify="left", wraplength=290,
                  foreground="#cccccc").grid(
            row=0, column=0, sticky="w", padx=8, pady=6)

        # ── Motion — WHERE sensation moves ────────────────────────────────────
        section(
            "WHERE  —  Spatial movement",
            "Controls how the active point moves across the electrode surface."
        )

        ab = cfg.get("alpha_beta_generation", {})
        self.cv_algo = tk.StringVar(value=ab.get("algorithm", "top-right-left"))

        # Algorithm picker with inline description
        algo_frame = ttk.Frame(parent)
        algo_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 0))
        algo_frame.columnconfigure(1, weight=1)
        row += 1
        ttk.Label(algo_frame, text="Path shape", font=("", 8, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        algo_combo = ttk.Combobox(
            algo_frame, textvariable=self.cv_algo, state="readonly",
            values=list(self._ALGO_INFO.keys()), width=20)
        algo_combo.grid(row=0, column=1, sticky="ew")

        self._algo_hint_var = tk.StringVar()
        ttk.Label(parent, textvariable=self._algo_hint_var,
                  font=("", 7), foreground="#4fc3f7", justify="left",
                  wraplength=300).grid(
            row=row, column=0, sticky="w", padx=12, pady=(1, 4))
        row += 1

        def _on_algo_change(*_):
            info = self._ALGO_INFO.get(self.cv_algo.get(), {})
            self._algo_hint_var.set(info.get("hint", ""))
            self._schedule_electrode_preview()
            self._schedule_sensation_update()

        self.cv_algo.trace_add("write", _on_algo_change)
        _on_algo_change()  # set initial hint

        # Electrode path mini-plot
        path_frame = ttk.LabelFrame(parent, text="Electrode path preview")
        path_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 4))
        path_frame.columnconfigure(0, weight=1)
        row += 1
        self._path_fig = Figure(figsize=(3.2, 1.8), tight_layout=True)
        self._path_canvas = FigureCanvas(self._path_fig, master=path_frame)
        self._path_canvas.get_tk_widget().pack(fill="both", expand=True)
        self._path_canvas.draw()

        self.cv_min_dist = tk.DoubleVar(value=ab.get("min_distance_from_center", 0.1))
        guided_slider(
            "Motion range  (center → edge)",
            "How far from center the sensation moves. "
            "Low = subtle, stays near center. High = wide sweep.",
            self.cv_min_dist, 0.05, 0.9,
            on_change=self._schedule_electrode_preview,
        )

        self.cv_pps = tk.IntVar(value=ab.get("points_per_second", 25))
        self.cv_speed_thresh = tk.IntVar(value=ab.get("speed_threshold_percent", 50))

        # ── Prostate ──────────────────────────────────────────────────────────
        pg = cfg.get("prostate_generation", {})
        self.cv_prostate_en = tk.BooleanVar(value=pg.get("generate_prostate_files", True))
        self.cv_prostate_algo = tk.StringVar(value=pg.get("algorithm", "tear-shaped"))

        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=4, pady=(6, 2))
        row += 1
        f_pr = ttk.Frame(parent)
        f_pr.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row += 1
        ttk.Checkbutton(f_pr, text="Generate prostate channel",
                        variable=self.cv_prostate_en).pack(side="left")
        ttk.Combobox(f_pr, textvariable=self.cv_prostate_algo, state="readonly",
                     values=["tear-shaped", "circular"], width=12).pack(
            side="left", padx=(8, 0))
        ttk.Label(f_pr, text="shape", font=("", 7), foreground="#666666").pack(
            side="left", padx=4)

        # ── Responsiveness — HOW FAST sensation tracks the action ─────────────
        section(
            "HOW FAST  —  Responsiveness to action",
            "Controls whether sensation builds gradually or reacts instantly to movement."
        )

        fq = cfg.get("frequency", {})

        self.cv_freq_ramp_ratio = tk.DoubleVar(
            value=fq.get("frequency_ramp_combine_ratio", 2.0))

        # Custom responsiveness slider with labeled endpoints
        hdr2 = ttk.Frame(parent)
        hdr2.grid(row=row, column=0, sticky="ew", padx=8, pady=(4, 0))
        hdr2.columnconfigure(1, weight=1)
        row += 1
        ttk.Label(hdr2, text="Tracking style", font=("", 8, "bold")).grid(
            row=0, column=0, sticky="w")
        self._ramp_val_lbl = ttk.Label(hdr2, text="", font=("", 8),
                                       foreground="#4fc3f7", width=24, anchor="e")
        self._ramp_val_lbl.grid(row=0, column=1, sticky="e")

        def _on_ramp(v):
            ratio = float(v)
            speed_pct = round((1 / ratio) * 100)
            ramp_pct = 100 - speed_pct
            if ratio <= 2:
                label = "Reactive — follows action closely"
            elif ratio <= 4:
                label = "Balanced — responsive with slow build"
            elif ratio <= 7:
                label = "Gradual — mostly slow build"
            else:
                label = "Slow build — ignores short spikes"
            self._ramp_val_lbl.config(text=label)
            self._ramp_hint_var.set(
                f"{speed_pct}% tracks action speed  •  {ramp_pct}% slow build"
            )
            self._schedule_sensation_update()

        ttk.Scale(parent, from_=1.0, to=10.0, variable=self.cv_freq_ramp_ratio,
                  orient="horizontal", command=_on_ramp).grid(
            row=row, column=0, sticky="ew", padx=8, pady=(0, 0))
        row += 1

        ep_row = ttk.Frame(parent)
        ep_row.grid(row=row, column=0, sticky="ew", padx=8)
        ep_row.columnconfigure(1, weight=1)
        row += 1
        ttk.Label(ep_row, text="Reactive", font=("", 7), foreground="#666666").grid(
            row=0, column=0, sticky="w")
        ttk.Label(ep_row, text="Slow build", font=("", 7), foreground="#666666").grid(
            row=0, column=2, sticky="e")

        self._ramp_hint_var = tk.StringVar()
        ttk.Label(parent, textvariable=self._ramp_hint_var,
                  font=("", 7), foreground="#4fc3f7", justify="left").grid(
            row=row, column=0, sticky="w", padx=12, pady=(0, 4))
        row += 1
        _on_ramp(self.cv_freq_ramp_ratio.get())  # set initial state

        self.cv_pulse_freq_ratio = tk.DoubleVar(
            value=fq.get("pulse_frequency_combine_ratio", 3.0))
        guided_slider(
            "Pulse rate blend",
            "How much action position (vs speed) shapes the pulse rate. "
            "Higher = position-driven, lower = speed-driven.",
            self.cv_pulse_freq_ratio, 1.0, 10.0,
        )

        self.cv_pf_min = tk.DoubleVar(value=fq.get("pulse_freq_min", 0.40))
        self.cv_pf_max = tk.DoubleVar(value=fq.get("pulse_freq_max", 0.95))
        guided_slider(
            "Pulse rate — minimum",
            "Slowest pulse rate (at rest / slow sections). "
            "0 = very slow, 1 = always fast.",
            self.cv_pf_min, 0.0, 1.0,
        )
        guided_slider(
            "Pulse rate — maximum",
            "Fastest pulse rate (during peak action). "
            "Should be higher than minimum.",
            self.cv_pf_max, 0.0, 1.0,
        )

        # ── Pulse feel — WHAT KIND of sensation ───────────────────────────────
        section(
            "WHAT KIND  —  Pulse character",
            "Controls the shape of each individual pulse — its fullness and how it attacks."
        )

        pu = cfg.get("pulse", {})

        self.cv_pw_min = tk.DoubleVar(value=pu.get("pulse_width_min", 0.1))
        self.cv_pw_max = tk.DoubleVar(value=pu.get("pulse_width_max", 0.45))
        guided_slider(
            "Width — narrow end",
            "Pulse width during low-intensity moments. "
            "Narrow = sharper, more distinct. Wide = fuller, more continuous.",
            self.cv_pw_min, 0.0, 1.0,
        )
        guided_slider(
            "Width — wide end",
            "Pulse width during peak intensity. "
            "Should be higher than narrow end.",
            self.cv_pw_max, 0.0, 1.0,
        )

        self.cv_pr_min = tk.DoubleVar(value=pu.get("pulse_rise_min", 0.0))
        self.cv_pr_max = tk.DoubleVar(value=pu.get("pulse_rise_max", 0.80))
        guided_slider(
            "Attack — sharpest",
            "How abruptly pulses start at low intensity. "
            "0 = immediate hard edge. 1 = slow, gentle onset.",
            self.cv_pr_min, 0.0, 1.0,
        )
        guided_slider(
            "Attack — softest",
            "How abruptly pulses start at peak intensity. "
            "Sweep from sharp to soft creates more varied texture.",
            self.cv_pr_max, 0.0, 1.0,
        )

        # ── Output mode ───────────────────────────────────────────────────────
        ttk.Separator(parent, orient="horizontal").grid(
            row=row, column=0, sticky="ew", padx=4, pady=(8, 4))
        row += 1
        ttk.Label(parent, text="Output channels", font=("", 9, "bold")).grid(
            row=row, column=0, sticky="w", padx=8)
        row += 1

        ax = cfg.get("positional_axes", {})
        self.cv_gen_3p = tk.BooleanVar(value=ax.get("generate_legacy", True))
        self.cv_gen_4p = tk.BooleanVar(value=ax.get("generate_motion_axis", True))

        f_mode = ttk.Frame(parent)
        f_mode.grid(row=row, column=0, sticky="ew", padx=8, pady=2)
        row += 1
        ttk.Checkbutton(f_mode, text="3-pole  (alpha / beta)",
                        variable=self.cv_gen_3p).pack(anchor="w")
        ttk.Label(f_mode, text="   Standard restim electrode position files",
                  font=("", 7), foreground="#666666").pack(anchor="w")
        ttk.Checkbutton(f_mode, text="4-pole  (E1 – E4)",
                        variable=self.cv_gen_4p).pack(anchor="w", pady=(4, 0))
        ttk.Label(f_mode, text="   For 4-electrode setups",
                  font=("", 7), foreground="#666666").pack(anchor="w")

        ttk.Frame(parent).grid(row=row, column=0, pady=10)

        # Initial electrode path preview
        self._schedule_electrode_preview()
        self._schedule_sensation_update()

    # ── Live preview helpers ───────────────────────────────────────────────────

    _electrode_preview_pending = False
    _sensation_update_pending = False

    def _schedule_electrode_preview(self, *_):
        """Debounce: schedule one electrode path redraw, ignore rapid slider moves."""
        if not self._electrode_preview_pending:
            self._electrode_preview_pending = True
            self.root.after(150, self._do_electrode_preview)

    def _do_electrode_preview(self):
        self._electrode_preview_pending = False
        algo = self.cv_algo.get()
        min_dist = self.cv_min_dist.get()

        def _run():
            try:
                from cli import preview_electrode_path
                data = preview_electrode_path(
                    algorithm=algo,
                    min_distance_from_center=min_dist,
                    points=120,
                )
                self.root.after(0, lambda: self._draw_electrode_plot(data))
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _draw_electrode_plot(self, data: dict):
        self._path_fig.clear()
        ax = self._path_fig.add_subplot(111)
        alpha = data.get("alpha", [])
        beta = data.get("beta", [])
        if alpha and beta:
            ax.plot(alpha, beta, linewidth=0.8, color="#4fc3f7", alpha=0.9)
            ax.scatter([alpha[0]], [beta[0]], color="#88ff88", s=18, zorder=5)
            ax.scatter([alpha[-1]], [beta[-1]], color="#ff8888", s=18, zorder=5)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("alpha", fontsize=7)
        ax.set_ylabel("beta", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.set_aspect("equal", adjustable="box")
        self._path_fig.tight_layout()
        self._path_canvas.draw()

    def _schedule_sensation_update(self, *_):
        if not self._sensation_update_pending:
            self._sensation_update_pending = True
            self.root.after(200, self._do_sensation_update)

    def _do_sensation_update(self):
        self._sensation_update_pending = False
        self._sensation_var.set(self._summarize_sensation())

    def _summarize_sensation(self) -> str:
        """Translate current creative settings into plain-language description."""
        parts = []

        # Motion
        info = self._ALGO_INFO.get(self.cv_algo.get(), {})
        algo_label = info.get("label", self.cv_algo.get())
        dist = self.cv_min_dist.get()
        if dist < 0.2:
            sweep = "subtle, close to center"
        elif dist < 0.5:
            sweep = "moderate sweep"
        else:
            sweep = "wide sweep, edge to edge"
        parts.append(f"Movement: {algo_label}. {sweep.capitalize()}.")

        # Responsiveness
        ratio = self.cv_freq_ramp_ratio.get()
        if ratio <= 2:
            parts.append("Highly reactive — tracks every stroke.")
        elif ratio <= 4:
            parts.append("Balanced — responsive with a gradual build.")
        elif ratio <= 7:
            parts.append("Mostly gradual — builds over the scene.")
        else:
            parts.append("Slow build — independent of individual strokes.")

        # Pulse character
        pw_mid = (self.cv_pw_min.get() + self.cv_pw_max.get()) / 2
        pr_mid = (self.cv_pr_min.get() + self.cv_pr_max.get()) / 2
        width_desc = "narrow" if pw_mid < 0.25 else ("wide" if pw_mid > 0.6 else "medium")
        attack_desc = "sharp" if pr_mid < 0.25 else ("soft" if pr_mid > 0.65 else "mixed")
        parts.append(f"Pulses: {width_desc} width, {attack_desc} attack.")

        return "  ".join(parts)

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
        if not self.source_data:
            return
        try:
            output_data = load_file(str(self.output_files[suffix]))
            self.after_label_frame.config(text=f"After — {suffix}")
            self._plot_comparison(
                self.after_fig, self.after_mpl,
                self.source_data, output_data, suffix
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
                info = load_file(str(path))
                self.root.after(0, lambda: self._on_file_loaded(path, info))
            except Exception as e:
                self.root.after(0, lambda: self._set_status(0, f"Failed to load: {e}"))

        threading.Thread(target=_do, daemon=True).start()

    def _on_file_loaded(self, path: Path, info: dict):
        self.input_file = path
        self.source_data = info

        self.lbl_filename.config(text=info["name"])
        self.lbl_actions.config(text=str(info["actions"]))
        self.lbl_duration.config(text=info["duration_fmt"])
        self.lbl_range.config(text=f"{int(info['pos_min'] * 100)} – {int(info['pos_max'] * 100)}")

        self.output_dir_var.set(str(path.parent))

        # Plots — pass info dict directly; _plot_funscript reads info["x"] / info["y"]
        self._plot_funscript(self.input_fig, self.input_mpl, info, "Input")
        self._plot_funscript(self.before_fig, self.before_mpl, info, "Original")
        self._plot_funscript(self.review_before_fig, self.review_before_mpl, info, "Original")

        self.drop_label.config(text=info["name"])
        self.notebook.tab(1, state="normal")
        self.btn_next_1.config(state="normal")
        self._set_status(100, f"Loaded {info['name']} — {info['actions']} actions, {info['duration_fmt']}")

    # ─── Visualization ────────────────────────────────────────────────────────

    def _plot_funscript(self, fig: Figure, canvas: FigureCanvas, data: dict, label: str):
        """Plot a funscript waveform. data is the dict returned by cli.load_file."""
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(data["x"], data["y"] * 100, linewidth=0.7, color="#4fc3f7", label=label)
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
        original: dict,
        processed: dict,
        label: str,
    ):
        """Overlay original vs processed waveform. Both are dicts from cli.load_file."""
        fig.clear()
        ax = fig.add_subplot(111)
        ax.plot(original["x"], original["y"] * 100, linewidth=0.5,
                color="#555555", alpha=0.6, label="original")
        ax.plot(processed["x"], processed["y"] * 100, linewidth=0.8,
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
            result = process(str(self.input_file), self.current_config, self._progress_callback)
            if result["success"]:
                self.output_files = {o["suffix"]: Path(o["path"]) for o in result["outputs"]}
                self.root.after(0, self._on_processing_done)
            else:
                msg = result.get("error", "Unknown error")
                self.root.after(0, lambda: self._set_status(0, f"Processing error: {msg}"))
                self.root.after(0, lambda: self.btn_process.config(state="normal"))
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
        if not self.source_data:
            return
        try:
            output_data = load_file(str(path))
            self.review_after_lf.config(text=f"Output: {suffix}")
            self._plot_comparison(
                self.review_after_fig, self.review_after_mpl,
                self.source_data, output_data, suffix
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
        self.source_data = None
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
