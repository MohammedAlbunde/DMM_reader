"""
Professional GUI to control waveform generator and read voltage from multimeter.
Author: Mohammed Al-Bunde
"""

import pyvisa
from tkinter import Tk, Label, Entry, Button, StringVar, OptionMenu, Frame

# --- Instrument connection ---
rm = pyvisa.ResourceManager()
# Assign VISA addresses directly
WAVEGEN_ADDR = 'USB0::0x0957::0x2507::MY58000690::INSTR'
DMM_ADDR     = 'USB0::0x2A8D::0x1701::MY57102012::INSTR'

try:
    wavegen = rm.open_resource(WAVEGEN_ADDR)
except Exception as e:
    wavegen = None
    print(f"Waveform generator not found: {e}")

try:
    multimeter = rm.open_resource(DMM_ADDR)
except Exception as e:
    multimeter = None
    print(f"Multimeter not found: {e}")

# --- GUI setup ---
root = Tk()
root.title("Waveform Generator & Multimeter Control")
root.geometry("400x320")
root.configure(bg="gray15")

# --- Input fields ---
frame = Frame(root, bg="gray15")
frame.pack(pady=20)

Label(frame, text="Waveform:", bg="gray15", fg="white", font=("Arial", 12)).grid(row=0, column=0, sticky="e")
waveform_var = StringVar(value="SIN")
OptionMenu(frame, waveform_var, "SIN", "SQU", "RAMP").grid(row=0, column=1)

Label(frame, text="Frequency (Hz):", bg="gray15", fg="white", font=("Arial", 12)).grid(row=1, column=0, sticky="e")
freq_entry = Entry(frame, font=("Arial", 12)); freq_entry.insert(0, "1000"); freq_entry.grid(row=1, column=1)

Label(frame, text="High Voltage (V):", bg="gray15", fg="white", font=("Arial", 12)).grid(row=2, column=0, sticky="e")
vhigh_entry = Entry(frame, font=("Arial", 12)); vhigh_entry.insert(0, "5.0"); vhigh_entry.grid(row=2, column=1)

Label(frame, text="Low Voltage (V):", bg="gray15", fg="white", font=("Arial", 12)).grid(row=3, column=0, sticky="e")
vlow_entry = Entry(frame, font=("Arial", 12)); vlow_entry.insert(0, "0.0"); vlow_entry.grid(row=3, column=1)

# --- Output display ---
result_var = StringVar(value="Measured Voltage: --- V")
Label(root, textvariable=result_var, font=("DS-Digital", 28), bg="black", fg="lime", width=20, relief="sunken").pack(pady=20)

# --- Control function ---
def set_waveform_and_measure():
    """Send waveform settings, measure voltage, update GUI."""
    if wavegen:
        wavegen.write("*RST")
        wavegen.write(f"FUNC {waveform_var.get()}")
        wavegen.write(f"FREQ {freq_entry.get()}")
        wavegen.write(f"VOLT:HIGH {vhigh_entry.get()}")
        wavegen.write(f"VOLT:LOW {vlow_entry.get()}")
        wavegen.write("OUTP ON")
    if multimeter:
        # Choose DMM mode based on waveform
        if waveform_var.get() == "SIN" or waveform_var.get() == "SQU":
            multimeter.write("CONF:VOLT:AC")
        else:
            multimeter.write("CONF:VOLT:DC")
        voltage = float(multimeter.query("READ?"))
        result_var.set(f"Measured Voltage: {voltage:.4f} V")

Button(root, text="Set & Measure", font=("Arial", 14, "bold"), bg="green", fg="white", command=set_waveform_and_measure).pack(pady=10)

root.mainloop()