"""
Control and visualize a function generator waveform in real time.

This script:
- Connects to a Keysight function generator via VISA.
- Prompts the user for waveform type, frequency, voltage levels, and duration in a GUI.
- Configures and outputs the waveform on the instrument.
- Plots the generated waveform live in a Tkinter GUI while the output is active.
- Resets the instrument after output.

Author: Mohammed Al-Bunde
"""

import pyvisa
import time
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import Tk, Label, Entry, Button, StringVar, Frame, OptionMenu
import threading

# Connect to instrument
rm = pyvisa.ResourceManager()
inst = rm.open_resource('USB0::0x0957::0x2507::MY58000690::INSTR')
inst.timeout = 5000
inst.write_termination = inst.read_termination = '\n'
print('Connected to:', inst.query('*IDN?').strip())

def configure_fgen(fgen, func, freq, v_high, v_low, duration):
    """Configure waveform and output, then reset instrument."""
    fgen.write('*RST')
    fgen.write(f'FUNC {func}')
    fgen.write(f'FREQ {freq}')
    fgen.write(f'VOLT:HIGH {v_high}')
    fgen.write(f'VOLT:LOW {v_low}')
    if func.upper() == 'SQU':
        fgen.write('FUNC:SQU:DCYC 50')
    fgen.write('OUTP1 ON')
    print(f'{func} wave on CH1 – {freq} Hz, {v_low}-{v_high} V.')
    time.sleep(duration)
    fgen.write('OUTP1 OFF')
    fgen.write('*RST')
    print('Output disabled, instrument reset.')

def live_plot_waveform(func, freq, v_high, v_low, duration):
    """Live plot waveform in a Tkinter GUI during output."""
    plot_root = Tk()
    plot_root.title("Live Generated Waveform")
    fig = Figure(figsize=(7, 3), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=plot_root)
    canvas.get_tk_widget().pack()
    start_time = time.time()

    def update_plot():
        elapsed = time.time() - start_time
        period = 1 / float(freq)
        window = 2 * period
        t0 = max(0, elapsed - window)
        t = np.linspace(t0, elapsed, int(1000 * window) if elapsed > 0 else 1)
        if func == 'SIN':
            y = (float(v_high) - float(v_low))/2 * np.sin(2 * np.pi * float(freq) * t) + (float(v_high) + float(v_low))/2
        elif func == 'SQU':
            y = np.where(np.sin(2 * np.pi * float(freq) * t) >= 0, float(v_high), float(v_low))
        elif func == 'RAMP':
            y = (float(v_high) - float(v_low)) * (t % period) / period + float(v_low)
        else:
            y = np.zeros_like(t)
        ax.clear()
        ax.plot(t, y, color='blue')
        ax.set_title(f"{func} Waveform (Live)")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Voltage (V)")
        ax.grid(True)
        canvas.draw()
        if elapsed < duration:
            plot_root.after(50, update_plot)
        else:
            plot_root.quit()

    update_plot()
    plot_root.mainloop()

def start_waveform():
    """Get user input from GUI, start generator and plot."""
    func = func_var.get()
    freq = freq_entry.get()
    v_high = vhigh_entry.get()
    v_low = vlow_entry.get()
    duration = float(duration_entry.get())
    # Start function generator output in a separate thread
    fgen_thread = threading.Thread(target=configure_fgen, args=(inst, func, freq, v_high, v_low, duration))
    fgen_thread.start()
    # Start live plotting
    live_plot_waveform(func, freq, v_high, v_low, duration)
    fgen_thread.join()
    inst.close()
    root.quit()

# --- GUI for user input ---
root = Tk()
root.title("Function Generator Control")

Label(root, text="Waveform Type:", font=("Arial", 12)).grid(row=0, column=0, padx=8, pady=8, sticky="e")
func_var = StringVar(root)
func_var.set("SIN")
OptionMenu(root, func_var, "SIN", "SQU", "RAMP").grid(row=0, column=1, padx=8, pady=8)

Label(root, text="Frequency (Hz):", font=("Arial", 12)).grid(row=1, column=0, padx=8, pady=8, sticky="e")
freq_entry = Entry(root, font=("Arial", 12))
freq_entry.insert(0, "1000")
freq_entry.grid(row=1, column=1, padx=8, pady=8)

Label(root, text="High Voltage (V):", font=("Arial", 12)).grid(row=2, column=0, padx=8, pady=8, sticky="e")
vhigh_entry = Entry(root, font=("Arial", 12))
vhigh_entry.insert(0, "2.0")
vhigh_entry.grid(row=2, column=1, padx=8, pady=8)

Label(root, text="Low Voltage (V):", font=("Arial", 12)).grid(row=3, column=0, padx=8, pady=8, sticky="e")
vlow_entry = Entry(root, font=("Arial", 12))
vlow_entry.insert(0, "0.0")
vlow_entry.grid(row=3, column=1, padx=8, pady=8)

Label(root, text="Duration (s):", font=("Arial", 12)).grid(row=4, column=0, padx=8, pady=8, sticky="e")
duration_entry = Entry(root, font=("Arial", 12))
duration_entry.insert(0, "1")
duration_entry.grid(row=4, column=1, padx=8, pady=8)

Button(root, text="Start", font=("Arial", 12, "bold"), command=start_waveform, bg="green", fg="white").grid(row=5, column=0, columnspan=2, pady=16)

root.mainloop()