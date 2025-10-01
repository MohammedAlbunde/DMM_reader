#!/usr/bin/env python3
"""
Professional bench-top GUI  –  complete, thread-safe, zero-leak shutdown
PSU slider 5-9 V  |  live DMM read-back  |  FULL FG control
STOP/EXIT closes **every** VISA session we ever opened.
"""

import pyvisa
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

RESOURCE_NAMES = {"PS": None, "DMM": None, "FGEN": None}
THEME = {
    "bg": "#f5f5f5",
    "fg": "#222",
    "ok": "#2ecc71",
    "warn": "#f39c12",
    "err": "#e74c3c",
}
rm = pyvisa.ResourceManager()


# ---------- instrument helpers ---------------------------------
def idn(instr):
    try:
        return instr.query("*IDN?").strip()
    except Exception as e:
        return f"IDN failed: {e}"


def auto_discover():
    resources = rm.list_resources()
    out = {}
    for rsc in resources:
        try:
            tmp = rm.open_resource(rsc, open_timeout=500)
            tmp.timeout = 1000
            idn_str = idn(tmp).lower()
            if "sorensen" in idn_str or "xdl" in idn_str:
                out["PS"] = rsc
            elif "3446" in idn_str or "34401" in idn_str or "dmm" in idn_str:
                out["DMM"] = rsc
            elif "335" in idn_str or "336" in idn_str:
                out["FGEN"] = rsc
            tmp.close()
        except Exception:
            continue
    return out


def configure_fgen(fgen):
    fgen.write("*RST")
    fgen.write("FUNC SQU")
    fgen.write("FREQ 1000")
    fgen.write("UNIT:VOLT HIGHL")
    fgen.write("VOLT:HIGH 1.0")
    fgen.write("VOLT:LOW 0.0")
    fgen.write("FUNC:SQU:DCYC 50")
    fgen.write("OUTP1 ON")


def configure_ps(ps):
    ps.write("*RST")
    ps.write("I1 2")
    ps.write("OP1 0")


# -------------- GUI --------------------------------------------
class BenchGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bench-Top Instrument Simulator")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)

        self.inst = None
        self.run_flag = True
        self.lock = threading.Lock()
        self._all_sessions = []  # track every opened resource

        self.build_ui()
        self.connect_instruments()

        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()

    # ---------- session tracking -----------------------------
    def open_resource_logged(self, alias):
        """Open resource and keep it in a list for unconditional close."""
        rsc = rm.open_resource(alias)
        rsc.timeout = 5000
        self._all_sessions.append(rsc)
        return rsc

    def init_instruments(self):
        inst = {}
        for k, alias in RESOURCE_NAMES.items():
            if alias is None:
                raise RuntimeError(f"{k} not assigned")
            inst[k] = self.open_resource_logged(alias)
        return inst

    # ---------- thread-safe wrappers -------------------------
    def ps_write(self, cmd):
        with self.lock:
            self.inst["PS"].write(cmd)

    def ps_query(self, cmd):
        with self.lock:
            return self.inst["PS"].query(cmd)

    def dmm_query(self, cmd):
        with self.lock:
            return self.inst["DMM"].query(cmd)

    def fg_write(self, cmd):
        with self.lock:
            self.inst["FGEN"].write(cmd)

    def fg_query(self, cmd):
        with self.lock:
            return self.inst["FGEN"].query(cmd)

    # ---------- UI build -------------------------------------
    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TSpinbox", arrowsize=12)
        style.configure("OK.TLabel", foreground=THEME["ok"])
        style.configure("WARN.TLabel", foreground=THEME["warn"])

        top = ttk.Frame(self)
        top.pack(padx=20, pady=20, fill="both")

        # ---- PSU ----
        ttk.Label(top, text="Power-Supply Voltage", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w")
        self.psu_set = tk.DoubleVar(value=5.0)
        self.psu_slider = ttk.Scale(top, from_=5, to=9, variable=self.psu_set, orient="horizontal",
                                    command=self.slider_moved)
        self.psu_slider.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.psu_lbl = ttk.Label(top, text="set: 5.0 V", font=("Arial", 12))
        self.psu_lbl.grid(row=2, column=0, sticky="w")
        self.psu_read_lbl = ttk.Label(top, text="PSU read: --", font=("Arial", 12))
        self.psu_read_lbl.grid(row=3, column=0, sticky="w")

        # ---- DMM ----
        ttk.Label(top, text="DMM reading", font=("Arial", 14, "bold")).grid(row=0, column=1, padx=40)
        self.dmm_lbl = ttk.Label(top, text="-- V", font=("Arial", 20))
        self.dmm_lbl.grid(row=1, column=1)
        self.bar = ttk.Progressbar(top, length=200, maximum=10, value=0)
        self.bar.grid(row=2, column=1, pady=5)

        # ---- FG controls ----
        fg = ttk.LabelFrame(top, text="Function Generator", padding=10)
        fg.grid(row=0, column=2, rowspan=4, padx=20, sticky="nsew")

        # waveform
        ttk.Label(fg, text="Waveform").grid(row=0, column=0, sticky="w")
        self.wave_var = tk.StringVar(value="SQU")
        wave_cb = ttk.Combobox(fg, textvariable=self.wave_var, values=["SIN", "SQU", "RAMP", "PULSE", "DC", "NOIS"], state="readonly", width=8)
        wave_cb.grid(row=0, column=1, padx=5)
        wave_cb.bind("<<ComboboxSelected>>", self.fg_update)

        # frequency
        ttk.Label(fg, text="Frequency (Hz)").grid(row=1, column=0, sticky="w")
        self.freq_var = tk.IntVar(value=1000)
        ttk.Spinbox(fg, from_=1, to=10_000_000, textvariable=self.freq_var, width=10).grid(row=1, column=1, padx=5)
        self.freq_var.trace_add("write", lambda *_: self.fg_update())

        # high / low levels
        ttk.Label(fg, text="High (V)").grid(row=2, column=0, sticky="w")
        self.high_var = tk.DoubleVar(value=1.0)
        ttk.Scale(fg, from_=-5, to=5, variable=self.high_var, orient="horizontal",
                  command=lambda _: self.fg_update()).grid(row=2, column=1, sticky="ew")
        self.high_lbl = ttk.Label(fg, text="1.0 V")
        self.high_lbl.grid(row=2, column=2)

        ttk.Label(fg, text="Low (V)").grid(row=3, column=0, sticky="w")
        self.low_var = tk.DoubleVar(value=0.0)
        ttk.Scale(fg, from_=-5, to=5, variable=self.low_var, orient="horizontal",
                  command=lambda _: self.fg_update()).grid(row=3, column=1, sticky="ew")
        self.low_lbl = ttk.Label(fg, text="0.0 V")
        self.low_lbl.grid(row=3, column=2)

        # duty cycle
        ttk.Label(fg, text="Duty %").grid(row=4, column=0, sticky="w")
        self.duty_var = tk.IntVar(value=50)
        self.duty_sp = ttk.Spinbox(fg, from_=1, to=99, textvariable=self.duty_var, width=5)
        self.duty_sp.grid(row=4, column=1, padx=5)
        self.duty_var.trace_add("write", lambda *_: self.fg_update())

        # output on/off
        self.out_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(fg, text="Output ON", variable=self.out_var,
                        command=self.fg_update).grid(row=5, column=0, columnspan=2, pady=8)

        # stop button
        ttk.Button(top, text="STOP / EXIT", command=self.safe_exit).grid(row=4, column=0, columnspan=3, pady=10)

        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)

    # -------------- FG update ---------------------------------
    def fg_update(self, *_):
        if not self.inst:
            return
        wav = self.wave_var.get()
        self.fg_write(f"FUNC {wav}")
        self.fg_write(f"FREQ {self.freq_var.get()}")
        hi = round(self.high_var.get(), 3)
        lo = round(self.low_var.get(), 3)
        self.fg_write(f"VOLT:HIGH {hi}")
        self.fg_write(f"VOLT:LOW {lo}")
        self.high_lbl.config(text=f"{hi} V")
        self.low_lbl.config(text=f"{lo} V")
        if wav in ("SQU", "PULSE"):
            self.fg_write(f"FUNC:SQU:DCYC {self.duty_var.get()}")
        self.fg_write(f"OUTP1 {1 if self.out_var.get() else 0}")

    # -------------- slider ------------------------------------
    def slider_moved(self, _):
        val = round(self.psu_set.get(), 1)
        self.psu_lbl.config(text=f"set: {val:.1f} V")
        self.ps_write(f"V1 {val}")

    # -------------- polling loop ------------------------------
    def poll_loop(self):
        while self.run_flag:
            if self.inst:
                try:
                    with self.lock:
                        reply = self.inst["PS"].query("V1?").strip()
                        v_ps = float(reply.split()[-1])
                        self.inst["DMM"].write("CONF:VOLT:DC 10")
                        time.sleep(0.1)
                        v_dmm = float(self.inst["DMM"].query("READ?"))
                    self.after(0, lambda: self.update_live_labels(v_ps, v_dmm))
                except Exception:
                    pass
            time.sleep(0.5)

    def update_live_labels(self, v_ps, v_dmm):
        self.psu_read_lbl.config(text=f"PSU read: {v_ps:.3f} V")
        self.dmm_lbl.config(text=f"{v_dmm:.3f} V")
        self.bar["value"] = abs(v_dmm)
        colour = "OK" if abs(v_dmm - v_ps) < 0.1 else "WARN"
        self.dmm_lbl.config(style=f"{colour}.TLabel")

    # -------------- connection / bullet-proof exit ------------
    def connect_instruments(self):
        try:
            discovered = auto_discover()
            for k in RESOURCE_NAMES:
                RESOURCE_NAMES[k] = discovered.get(k)
                if RESOURCE_NAMES[k] is None:
                    raise RuntimeError(f"{k} not found")
            self.inst = self.init_instruments()
            configure_fgen(self.inst["FGEN"])
            configure_ps(self.inst["PS"])
            self.ps_write("OP1 1")
        except Exception as e:
            messagebox.showerror("Hardware error", str(e))
            self.safe_exit()

    def safe_exit(self):
        """Guaranteed shutdown: stop outputs + close **every** session."""
        self.run_flag = False
        try:
            if self.inst:
                with self.lock:
                    self.inst["PS"].write("OP1 0")
                    self.inst["FGEN"].write("OUTP1 OFF")
        except Exception:
            pass

        # close every single session we ever opened
        for ses in self._all_sessions:
            try:
                ses.close()
            except Exception:
                pass
        # final VISA manager close
        try:
            rm.close()
        except Exception:
            pass

        self.quit()
        self.destroy()


# ---------------- main ----------------------------------------
if __name__ == "__main__":
    BenchGUI().mainloop()