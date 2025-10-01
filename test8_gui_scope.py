#!/usr/bin/env python3
"""
Professional bench-top GUI  –  complete, thread-safe, zero-leak shutdown
PSU slider 5-9 V  |  live DMM read-back  |  FULL FG control | OSC control
STOP/EXIT closes **every** VISA session we ever opened.
"""

import pyvisa
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Add "OSC" for Oscilloscope to the dictionary of resource names.
RESOURCE_NAMES = {"PS": None, "DMM": None, "FGEN": None, "OSC": None}
# Define a color and theme scheme for the GUI elements.
THEME = {
    "bg": "#f5f5f5",
    "fg": "#222",
    "ok": "#2ecc71",
    "warn": "#f39c12",
    "err": "#e74c3c",
}
# Create a ResourceManager object, the main entry point for PyVISA.
rm = pyvisa.ResourceManager()


# ---------- instrument helpers ---------------------------------
# Defines a function to query an instrument's identification string (*IDN?).
def idn(instr):
    try:
        # Send the *IDN? query and return the stripped response.
        return instr.query("*IDN?").strip()
    except Exception as e:
        # If the query fails, return an error message.
        return f"IDN failed: {e}"

# Defines a function to automatically discover and categorize connected instruments.
def auto_discover():
    # Get a list of all available VISA resources.
    resources = rm.list_resources()
    # Initialize an empty dictionary to store categorized resource names.
    out = {}
    # Loop through each resource string.
    for rsc in resources:
        try:
            # Attempt to open a connection to the resource with a short timeout.
            tmp = rm.open_resource(rsc, open_timeout=500)
            # Set a 1-second timeout for subsequent communication.
            tmp.timeout = 1000
            # Get the instrument's identification string in lowercase for matching.
            idn_str = idn(tmp).lower()
            # Check for power supply keywords in the ID string.
            if "sorensen" in idn_str or "xdl" in idn_str:
                out["PS"] = rsc
            # Check for DMM keywords in the ID string.
            elif "3446" in idn_str or "34401" in idn_str or "dmm" in idn_str:
                out["DMM"] = rsc
            # Check for function generator keywords in the ID string.
            elif "335" in idn_str or "336" in idn_str:
                out["FGEN"] = rsc
            # Check for Tektronix oscilloscope keywords in the ID string.
            elif "tektronix" in idn_str and ("dpo20" in idn_str or "mso20" in idn_str):
                out["OSC"] = rsc
            # Close the temporary connection to free the resource.
            tmp.close()
        except Exception:
            # If an error occurs (e.g., resource is busy), skip to the next one.
            continue
    # Return the dictionary of discovered instruments.
    return out

# Defines a function to configure the function generator to a default state.
def configure_fgen(fgen):
    fgen.write("*RST")                 # Reset the instrument.
    fgen.write("FUNC SQU")              # Set waveform to Square.
    fgen.write("FREQ 1000")             # Set frequency to 1 kHz.
    fgen.write("UNIT:VOLT HIGHL")       # Set voltage units to High/Low levels.
    fgen.write("VOLT:HIGH 1.0")         # Set high level to 1.0 V.
    fgen.write("VOLT:LOW 0.0")          # Set low level to 0.0 V.
    fgen.write("FUNC:SQU:DCYC 50")      # Set duty cycle to 50%.
    fgen.write("OUTP1 ON")              # Turn the output on.

# Defines a function to configure the power supply to a default state.
def configure_ps(ps):
    ps.write("*RST")    # Reset the instrument.
    ps.write("I1 2")    # Set current limit on output 1 to 2A.
    ps.write("OP1 0")   # Ensure output 1 is off initially.

# Defines a function to configure the oscilloscope to a default state.
def configure_osc(osc):
    osc.write("*RST")               # Reset the instrument to default settings.
    osc.write("SELect:CH1 ON")      # Turn on Channel 1.
    osc.write("CH1:SCAle 1.0")      # Set Channel 1 vertical scale to 1 V/div.
    osc.write("DATa:ENCdg RIBinary") # Set waveform data encoding to signed binary.
    osc.write("DATa:WIDth 1")       # Set waveform data width to 1 byte.
    osc.write("ACQuire:STATE RUN")  # Start acquisition.

# -------------- GUI --------------------------------------------
# Defines the main application class, inheriting from Tkinter's root window.
class BenchGUI(tk.Tk):
    # The constructor method for the class.
    def __init__(self):
        # Call the parent class (tk.Tk) constructor.
        super().__init__()
        # Set the text in the window's title bar.
        self.title("Bench-Top Instrument Control")
        # Set the window's background color from the theme.
        self.configure(bg=THEME["bg"])
        # Prevent the user from resizing the window.
        self.resizable(False, False)

        # Initialize instance variable to hold connected instrument objects.
        self.inst = None
        # Initialize a flag to control the background polling thread.
        self.run_flag = True
        # Create a Lock to ensure thread-safe instrument access.
        self.lock = threading.Lock()
        # Create a list to track all opened VISA sessions for a clean shutdown.
        self._all_sessions = []

        # Call the method to build the GUI widgets.
        self.build_ui()
        # Call the method to discover and connect to instruments.
        self.connect_instruments()

        # Create a background thread for the instrument polling loop.
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        # Start the background thread.
        self.poll_thread.start()

    # ---------- session tracking -----------------------------
    # Defines a method that opens a resource and adds it to the tracking list.
    def open_resource_logged(self, alias):
        """Open resource and keep it in a list for unconditional close."""
        # Open the VISA resource using its string alias.
        rsc = rm.open_resource(alias)
        # Set a 5-second communication timeout for this resource.
        rsc.timeout = 5000
        # Add the new session object to the tracking list.
        self._all_sessions.append(rsc)
        # Return the instrument object.
        return rsc

    # Defines a method to initialize connections for all required instruments.
    def init_instruments(self):
        # Create an empty dictionary to hold the instrument objects.
        inst = {}
        # Loop through the required instruments (PS, DMM, FGEN, OSC).
        for k, alias in RESOURCE_NAMES.items():
            # Check if an instrument was not found during discovery.
            if alias is None:
                # If a required instrument is missing, raise an error.
                raise RuntimeError(f"{k} not found")
            # Open the resource using the logged method and store the object.
            inst[k] = self.open_resource_logged(alias)
        # Return the dictionary of connected instrument objects.
        return inst

    # ---------- thread-safe wrappers -------------------------
    # Defines a thread-safe method to write a command to the power supply.
    def ps_write(self, cmd):
        with self.lock:
            self.inst["PS"].write(cmd)

    # Defines a thread-safe method to query the power supply.
    def ps_query(self, cmd):
        with self.lock:
            return self.inst["PS"].query(cmd)

    # Defines a thread-safe method to query the DMM.
    def dmm_query(self, cmd):
        with self.lock:
            return self.inst["DMM"].query(cmd)

    # Defines a thread-safe method to write a command to the function generator.
    def fg_write(self, cmd):
        with self.lock:
            self.inst["FGEN"].write(cmd)

    # Defines a thread-safe method to query the function generator.
    def fg_query(self, cmd):
        with self.lock:
            return self.inst["FGEN"].query(cmd)

    # Defines a thread-safe method to write a command to the oscilloscope.
    def osc_write(self, cmd):
        with self.lock:
            self.inst["OSC"].write(cmd)
            
    # Defines a thread-safe method to query the oscilloscope.
    def osc_query(self, cmd):
        with self.lock:
            return self.inst["OSC"].query(cmd)

    # ---------- UI build -------------------------------------
    # Defines the method that creates all the GUI elements.
    def build_ui(self):
        # Create a Style object to customize widget appearance.
        style = ttk.Style(self)
        # Select the 'clam' theme for a modern look.
        style.theme_use("clam")
        # Configure all Spinbox widgets to have larger arrows.
        style.configure("TSpinbox", arrowsize=12)
        # Create a custom style for green "OK" labels.
        style.configure("OK.TLabel", foreground=THEME["ok"])
        # Create a custom style for orange "Warning" labels.
        style.configure("WARN.TLabel", foreground=THEME["warn"])

        # Create a main frame to hold all other widgets.
        top = ttk.Frame(self)
        # Add the frame to the window with padding.
        top.pack(padx=10, pady=10, fill="both", expand=True)

        # Create a master frame to hold instrument control panels.
        controls_frame = ttk.Frame(top)
        controls_frame.grid(row=0, column=0, columnspan=4, sticky='nsew', padx=5, pady=5)
        
        # --- Create a sub-frame for PSU and DMM ---
        psu_dmm_frame = ttk.Frame(controls_frame)
        psu_dmm_frame.grid(row=0, column=0, sticky='ns', padx=10, pady=10)

        # ---- PSU ----
        # Create a title label for the Power Supply section.
        ttk.Label(psu_dmm_frame, text="Power Supply", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w", columnspan=2)
        # Create a Tkinter variable to hold the slider's value.
        self.psu_set = tk.DoubleVar(value=5.0)
        # Create the voltage slider widget.
        self.psu_slider = ttk.Scale(psu_dmm_frame, from_=5, to=9, variable=self.psu_set, orient="horizontal", command=self.slider_moved)
        self.psu_slider.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        # Create a label to show the slider's set value.
        self.psu_lbl = ttk.Label(psu_dmm_frame, text="Set: 5.0 V", font=("Arial", 12))
        self.psu_lbl.grid(row=2, column=0, columnspan=2, sticky="w")
        # Create a label for the PSU's read-back voltage.
        self.psu_read_lbl = ttk.Label(psu_dmm_frame, text="PSU Read: --", font=("Arial", 12))
        self.psu_read_lbl.grid(row=3, column=0, columnspan=2, sticky="w")
        
        # Add a separator for visual clarity.
        ttk.Separator(psu_dmm_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky='ew', pady=15)

        # ---- DMM ----
        # Create a title label for the DMM section.
        ttk.Label(psu_dmm_frame, text="DMM Reading", font=("Arial", 14, "bold")).grid(row=5, column=0, columnspan=2)
        # Create the main label to display the DMM voltage reading.
        self.dmm_lbl = ttk.Label(psu_dmm_frame, text="-- V", font=("Arial", 20))
        self.dmm_lbl.grid(row=6, column=0, columnspan=2)
        # Create a progress bar to visually represent the DMM voltage.
        self.bar = ttk.Progressbar(psu_dmm_frame, length=150, maximum=10, value=0)
        self.bar.grid(row=7, column=0, columnspan=2, pady=5)
        
        # Add a vertical separator between panels.
        ttk.Separator(controls_frame, orient='vertical').grid(row=0, column=1, sticky='ns', padx=10, pady=10)

        # ---- FG controls ----
        # Create a labeled frame to group the Function Generator controls.
        fg = ttk.LabelFrame(controls_frame, text="Function Generator", padding=10)
        fg.grid(row=0, column=2, sticky="ns", padx=10, pady=10)
        # ... (FG UI elements remain the same as the original code) ...
        ttk.Label(fg, text="Waveform").grid(row=0, column=0, sticky="w")
        self.wave_var = tk.StringVar(value="SQU")
        wave_cb = ttk.Combobox(fg, textvariable=self.wave_var, values=["SIN", "SQU", "RAMP", "PULSE", "DC", "NOIS"], state="readonly", width=8)
        wave_cb.grid(row=0, column=1, padx=5)
        wave_cb.bind("<<ComboboxSelected>>", self.fg_update)
        ttk.Label(fg, text="Frequency (Hz)").grid(row=1, column=0, sticky="w")
        self.freq_var = tk.IntVar(value=1000)
        ttk.Spinbox(fg, from_=1, to=10_000_000, textvariable=self.freq_var, width=10, command=self.fg_update).grid(row=1, column=1, padx=5)
        ttk.Label(fg, text="High (V)").grid(row=2, column=0, sticky="w")
        self.high_var = tk.DoubleVar(value=1.0)
        ttk.Scale(fg, from_=-5, to=5, variable=self.high_var, orient="horizontal", command=self.fg_update).grid(row=2, column=1, sticky="ew")
        self.high_lbl = ttk.Label(fg, text="1.0 V")
        self.high_lbl.grid(row=2, column=2)
        ttk.Label(fg, text="Low (V)").grid(row=3, column=0, sticky="w")
        self.low_var = tk.DoubleVar(value=0.0)
        ttk.Scale(fg, from_=-5, to=5, variable=self.low_var, orient="horizontal", command=self.fg_update).grid(row=3, column=1, sticky="ew")
        self.low_lbl = ttk.Label(fg, text="0.0 V")
        self.low_lbl.grid(row=3, column=2)
        ttk.Label(fg, text="Duty %").grid(row=4, column=0, sticky="w")
        self.duty_var = tk.IntVar(value=50)
        self.duty_sp = ttk.Spinbox(fg, from_=1, to=99, textvariable=self.duty_var, width=5, command=self.fg_update)
        self.duty_sp.grid(row=4, column=1, padx=5)
        self.out_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(fg, text="Output ON", variable=self.out_var, command=self.fg_update).grid(row=5, column=0, columnspan=2, pady=8)
        
        # Add a vertical separator between panels.
        ttk.Separator(controls_frame, orient='vertical').grid(row=0, column=3, sticky='ns', padx=10, pady=10)
        
        # ---- Oscilloscope controls ----
        # Create a labeled frame to group the Oscilloscope controls.
        osc = ttk.LabelFrame(controls_frame, text="Oscilloscope", padding=10)
        osc.grid(row=0, column=4, sticky="ns", padx=10, pady=10)

        # Create a frame for the main action buttons.
        osc_actions = ttk.Frame(osc)
        osc_actions.grid(row=0, column=0, columnspan=3, pady=5)
        # Create and place the Autoset button.
        ttk.Button(osc_actions, text="Autoset", command=self.osc_autoset_clicked).pack(side="left", padx=2)
        # Create and place the Run button.
        ttk.Button(osc_actions, text="Run", command=lambda: self.osc_write("ACQuire:STATE RUN")).pack(side="left", padx=2)
        # Create and place the Stop button.
        ttk.Button(osc_actions, text="Stop", command=lambda: self.osc_write("ACQuire:STATE STOP")).pack(side="left", padx=2)
        # Create and place the Single button.
        ttk.Button(osc_actions, text="Single", command=self.osc_single_clicked).pack(side="left", padx=2)
        
        # Create a frame for the horizontal controls.
        osc_horiz = ttk.LabelFrame(osc, text="Horizontal", padding=5)
        osc_horiz.grid(row=1, column=0, columnspan=3, pady=5, sticky='ew')
        # Create and place the label for the horizontal position slider.
        ttk.Label(osc_horiz, text="Position").grid(row=0, column=0, sticky='w')
        # Create a Tkinter variable to hold the horizontal position.
        self.osc_hpos_var = tk.DoubleVar(value=50.0)
        # Create the slider for horizontal position (0 to 100%).
        ttk.Scale(osc_horiz, from_=0, to=100, variable=self.osc_hpos_var, orient="horizontal", command=self.osc_horiz_update).grid(row=1, column=0, columnspan=2, sticky='ew')
        # Create and place the label for the horizontal scale spinbox.
        ttk.Label(osc_horiz, text="Scale (s/div)").grid(row=2, column=0, sticky='w')
        # Create a Tkinter variable for the horizontal scale.
        self.osc_hscale_var = tk.StringVar(value="1ms")
        # Define a list of standard timebase values.
        h_scales = [f"{v}{u}" for u in ('ns', 'us', 'ms', 's') for v in (1, 2, 5, 10, 20, 50, 100, 200, 500)]
        # Create the spinbox for horizontal scale selection.
        ttk.Spinbox(osc_horiz, values=h_scales, textvariable=self.osc_hscale_var, width=8, command=self.osc_horiz_update, wrap=True).grid(row=2, column=1, sticky='e')

        # Create a frame for the Channel 1 controls.
        osc_ch1 = ttk.LabelFrame(osc, text="Channel 1", padding=5)
        osc_ch1.grid(row=2, column=0, columnspan=3, pady=5, sticky='ew')
        # Create a Tkinter variable for the CH1 enable checkbox.
        self.osc_ch1_en_var = tk.BooleanVar(value=True)
        # Create the checkbox to turn Channel 1 on or off.
        ttk.Checkbutton(osc_ch1, text="CH1 ON", variable=self.osc_ch1_en_var, command=self.osc_ch1_update).grid(row=0, column=0, sticky='w', columnspan=2)
        # Create and place the label for the vertical position slider.
        ttk.Label(osc_ch1, text="Position").grid(row=1, column=0, sticky='w')
        # Create a Tkinter variable for the CH1 vertical position.
        self.osc_vpos_var = tk.DoubleVar(value=0.0)
        # Create the slider for vertical position (-4 to +4 divisions).
        ttk.Scale(osc_ch1, from_=-4, to=4, variable=self.osc_vpos_var, orient="horizontal", command=self.osc_ch1_update).grid(row=2, column=0, columnspan=2, sticky='ew')
        # Create and place the label for the vertical scale spinbox.
        ttk.Label(osc_ch1, text="Scale (V/div)").grid(row=3, column=0, sticky='w')
        # Create a Tkinter variable for the vertical scale.
        self.osc_vscale_var = tk.StringVar(value="1.0")
        # Define a list of standard vertical scale values.
        v_scales = [f"{v/1000.0:.3f}" for v in (1,2,5,10,20,50,100,200,500)] + [f"{v:.1f}" for v in (1,2,5)]
        # Create the spinbox for vertical scale selection.
        ttk.Spinbox(osc_ch1, values=v_scales, textvariable=self.osc_vscale_var, width=6, command=self.osc_ch1_update, wrap=True).grid(row=3, column=1, sticky='e')
        
        # Create a button to save a screenshot to a USB drive in the scope.
        ttk.Button(osc, text="Save Screen to USB", command=self.osc_save_screen).grid(row=3, column=0, columnspan=3, pady=10)

        # ---- Global stop button ----
        # Create and place the main application STOP/EXIT button.
        ttk.Button(top, text="STOP / EXIT ALL", command=self.safe_exit).grid(row=1, column=0, columnspan=4, pady=10, sticky='ew')

    # -------------- Oscilloscope callbacks ------------------------
    # Callback for the Autoset button.
    def osc_autoset_clicked(self, *_):
        if self.inst: self.osc_write("AUTOSet EXECute")

    # Callback for the Single Acquisition button.
    def osc_single_clicked(self, *_):
        if self.inst:
            self.osc_write("ACQuire:STOPAfter SEQuence")
            self.osc_write("ACQuire:STATE ON")

    # Callback to save a screen image. Saves to a USB drive in the scope.
    def osc_save_screen(self, *_):
        if self.inst:
            # Set image format to PNG.
            self.osc_write("SAVe:IMAGe:FILEFormat PNG")
            # Execute the save command. File is saved to the USB drive's root.
            self.osc_write('SAVe:IMAGe "E:/scope_capture.png"')
            # Show an info message to the user.
            messagebox.showinfo("Screenshot", "Saved image to scope's USB drive as 'E:/scope_capture.png'")

    # Callback for any change in the Channel 1 controls.
    def osc_ch1_update(self, *_):
        if not self.inst: return
        # Turn the channel on or off based on the checkbox.
        self.osc_write(f"SELect:CH1 {1 if self.osc_ch1_en_var.get() else 0}")
        # Set the vertical position from the slider.
        self.osc_write(f"CH1:POSition {self.osc_vpos_var.get():.2f}")
        # Set the vertical scale from the spinbox.
        self.osc_write(f"CH1:SCAle {self.osc_vscale_var.get()}")

    # Callback for any change in the Horizontal controls.
    def osc_horiz_update(self, *_):
        if not self.inst: return
        # Set the horizontal position from the slider.
        self.osc_write(f"HORizontal:POSition {self.osc_hpos_var.get():.2f}")
        # Parse the string from the spinbox (e.g., "1ms" -> 1e-3).
        val_str = self.osc_hscale_var.get()
        multipliers = {'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1}
        for unit, mult in multipliers.items():
            if val_str.endswith(unit):
                num = float(val_str[:-len(unit)])
                # Send the final scaled value to the instrument.
                self.osc_write(f"HORizontal:SCAle {num * mult}")
                break

    # -------------- FG update ---------------------------------
    # Callback for any change in the function generator controls.
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
        self.high_lbl.config(text=f"{hi:.1f} V")
        self.low_lbl.config(text=f"{lo:.1f} V")
        if wav in ("SQU", "PULSE"):
            self.fg_write(f"FUNC:SQU:DCYC {self.duty_var.get()}")
        self.fg_write(f"OUTP1 {1 if self.out_var.get() else 0}")

    # -------------- slider ------------------------------------
    # Callback for when the PSU slider is moved.
    def slider_moved(self, _):
        val = round(self.psu_set.get(), 1)
        self.psu_lbl.config(text=f"Set: {val:.1f} V")
        self.ps_write(f"V1 {val}")

    # -------------- polling loop ------------------------------
    # The main function for the background thread that reads from instruments.
    def poll_loop(self):
        while self.run_flag:
            if self.inst:
                try:
                    # Acquire the lock for exclusive, thread-safe access.
                    with self.lock:
                        # Query the power supply for its current voltage setting.
                        reply = self.inst["PS"].query("V1?").strip()
                        # Parse the reply to get the voltage as a float.
                        v_ps = float(reply.split()[-1])
                        # Configure the DMM to measure DC voltage on the 10V range.
                        self.inst["DMM"].write("CONF:VOLT:DC 10")
                        # Pause briefly to allow the DMM to configure.
                        time.sleep(0.1)
                        # Take a reading from the DMM.
                        v_dmm = float(self.inst["DMM"].query("READ?"))
                    # Schedule the GUI update to run on the main (GUI) thread.
                    self.after(0, lambda: self.update_live_labels(v_ps, v_dmm))
                except Exception:
                    # If any communication error occurs, ignore it and continue polling.
                    pass
            # Pause for half a second before the next poll cycle.
            time.sleep(0.5)

    # Method to update the live GUI labels with data from the polling loop.
    def update_live_labels(self, v_ps, v_dmm):
        self.psu_read_lbl.config(text=f"PSU Read: {v_ps:.3f} V")
        self.dmm_lbl.config(text=f"{v_dmm:.3f} V")
        self.bar["value"] = abs(v_dmm)
        # Determine status color based on difference between set and measured voltage.
        colour = "OK" if abs(v_dmm - v_ps) < 0.1 else "WARN"
        # Apply the appropriate style (green or orange) to the DMM label.
        self.dmm_lbl.config(style=f"{colour}.TLabel")

    # -------------- connection / bullet-proof exit ------------
    # Handles the initial discovery and connection process for all instruments.
    def connect_instruments(self):
        try:
            # Call the discovery function to find all instruments.
            discovered = auto_discover()
            # Assign the found resource strings to the global dictionary.
            for k in RESOURCE_NAMES:
                RESOURCE_NAMES[k] = discovered.get(k)
                # If a required instrument is missing, raise a critical error.
                if RESOURCE_NAMES[k] is None:
                    raise RuntimeError(f"Required instrument '{k}' not found!")
            # Initialize connections to all found instruments.
            self.inst = self.init_instruments()
            # Configure the instruments to their default states.
            configure_fgen(self.inst["FGEN"])
            configure_ps(self.inst["PS"])
            configure_osc(self.inst["OSC"])
            # Turn the power supply output on.
            self.ps_write("OP1 1")
        except Exception as e:
            # If any error occurs during setup, show a popup and exit safely.
            messagebox.showerror("Hardware Error", str(e))
            self.safe_exit()

    # Defines the method to safely shut down the application and all hardware.
    def safe_exit(self):
        """Guaranteed shutdown: stop outputs + close **every** session."""
        # Set the flag to false to stop the background polling thread.
        self.run_flag = False
        try:
            # Check if instruments were ever connected.
            if self.inst:
                # Acquire the lock for safe access.
                with self.lock:
                    # Turn off all instrument outputs to ensure a safe state.
                    self.inst["PS"].write("OP1 0")
                    self.inst["FGEN"].write("OUTP1 OFF")
                    self.inst["OSC"].write("ACQuire:STATE STOP")
        except Exception:
            # Ignore errors during shutdown to ensure the process completes.
            pass

        # Close every single VISA session that was ever opened.
        for ses in self._all_sessions:
            try:
                # Attempt to close the session.
                ses.close()
            except Exception:
                # Ignore errors if a session is already closed or invalid.
                pass
        # Final close of the main VISA resource manager.
        try:
            rm.close()
        except Exception:
            pass

        # Tell the Tkinter mainloop to exit.
        self.quit()
        # Destroy the Tkinter window and its widgets.
        self.destroy()


# ---------------- main ----------------------------------------
# Standard Python entry point: this code runs only when the script is executed directly.
if __name__ == "__main__":
    # Create an instance of the main application class.
    app = BenchGUI()
    # Set the protocol for the window's close button to call safe_exit.
    app.protocol("WM_DELETE_WINDOW", app.safe_exit)
    # Start the Tkinter event loop.
    app.mainloop()