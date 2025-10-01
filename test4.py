#!/usr/bin/env python3
"""
Professional bench-top GUI
PSU slider 5-9 V  |  live DMM read-back  |  1 kHz 0-1 V square on FG
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
    """Return dict with first matching resource for each class."""
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

def init_instruments():
    inst = {}
    for k, alias in RESOURCE_NAMES.items():
        if alias is None:
            raise RuntimeError(f"{k} not assigned")
        inst[k] = rm.open_resource(alias)
        inst[k].timeout = 5000
    return inst

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

# ---------- GUI -------------------------------------------------
class BenchGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bench-Top Instrument Simulator")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)

        self.inst = None
        self.run_flag = True

        self.build_ui()
        self.connect_instruments()

        # polling thread
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()

    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("OK.TLabel", foreground=THEME["ok"])
        style.configure("WARN.TLabel", foreground=THEME["warn"])
        style.configure("ERR.TLabel", foreground=THEME["err"])

        top = ttk.Frame(self)
        top.pack(padx=20, pady=20, fill="both")

        # PSU section
        ttk.Label(top, text="Power-Supply Voltage", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w")
        self.psu_set = tk.DoubleVar(value=5.0)
        self.psu_slider = ttk.Scale(top, from_=5, to=9, variable=self.psu_set, orient="horizontal",
                                    command=self.slider_moved)
        self.psu_slider.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.psu_lbl = ttk.Label(top, text="set: 5.0 V", font=("Arial", 12))
        self.psu_lbl.grid(row=2, column=0, sticky="w")

        self.psu_read_lbl = ttk.Label(top, text="PSU read: --", font=("Arial", 12))
        self.psu_read_lbl.grid(row=3, column=0, sticky="w")

        # DMM section
        ttk.Label(top, text="DMM reading", font=("Arial", 14, "bold")).grid(row=0, column=1, padx=40)
        self.dmm_lbl = ttk.Label(top, text="-- V", font=("Arial", 20))
        self.dmm_lbl.grid(row=1, column=1)

        # progress bar
        self.bar = ttk.Progressbar(top, length=200, maximum=10, value=0)
        self.bar.grid(row=2, column=1, pady=5)

        # FG label
        ttk.Label(top, text="Generator", font=("Arial", 14, "bold")).grid(row=0, column=2)
        ttk.Label(top, text="1 kHz  0-1 V  square  CH1", font=("Arial", 12)).grid(row=1, column=2)

        # stop button
        ttk.Button(top, text="STOP / EXIT", command=self.safe_exit).grid(row=3, column=2, pady=10)

        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(2, weight=1)

    def connect_instruments(self):
        try:
            discovered = auto_discover()
            for k in RESOURCE_NAMES:
                RESOURCE_NAMES[k] = discovered.get(k)
                if RESOURCE_NAMES[k] is None:
                    raise RuntimeError(f"{k} not found")
            self.inst = init_instruments()
            configure_fgen(self.inst["FGEN"])
            configure_ps(self.inst["PS"])
            self.inst["PS"].write("OP1 1")  # enable output
        except Exception as e:
            messagebox.showerror("Hardware error", str(e))
            self.safe_exit()

    def slider_moved(self, _):
        val = round(self.psu_set.get(), 1)
        self.psu_lbl.config(text=f"set: {val:.1f} V")
        if self.inst:
            self.inst["PS"].write(f"V1 {val}")

    def poll_loop(self):
        while self.run_flag:
            if self.inst:
                try:
                    # PSU read-back
                    reply = self.inst["PS"].query("V1?").strip()
                    v_ps = float(reply.split()[-1])
                    self.psu_read_lbl.config(text=f"PSU read: {v_ps:.3f} V")

                    # DMM
                    self.inst["DMM"].write("CONF:VOLT:DC 10")
                    time.sleep(0.1)
                    v_dmm = float(self.inst["DMM"].query("READ?"))
                    self.dmm_lbl.config(text=f"{v_dmm:.3f} V")
                    self.bar["value"] = abs(v_dmm)
                    colour = "OK" if abs(v_dmm - v_ps) < 0.1 else "WARN"
                    self.dmm_lbl.config(style=f"{colour}.TLabel")
                except Exception:
                    pass
            time.sleep(0.5)

    def safe_exit(self):
        self.run_flag = False
        if self.inst:
            try:
                self.inst["PS"].write("OP1 0")
                self.inst["FGEN"].write("OUTP1 OFF")
            except Exception:
                pass
            for i in self.inst.values():
                i.close()
        self.quit()
        self.destroy()

# ---------- main ------------------------------------------------
if __name__ == "__main__":
    BenchGUI().mainloop()