#!/usr/bin/env python3
"""
Live DMM logger → SQLite
Author:Mohammed Al-Bunde (Mohammed Al-Nidawi)
"""
import pyvisa
import sqlite3
import datetime as dt
import time
import signal
import sys
import os
from tkinter import Tk, Label, StringVar

# --- Config ---
DB_FILE, TABLE = "dmm_log.db", "readings"
DMM_VISA, POLL_SEC = "USB0::0x2A8D::0x1701::MY57102012::INSTR", 1.0

# --- Always start with a fresh DB ---
if os.path.exists(DB_FILE): os.remove(DB_FILE)

# --- Create DB table ---
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()
cur.execute(f"""CREATE TABLE {TABLE} (
    id INTEGER PRIMARY KEY, utc TEXT, value REAL, unit TEXT, function TEXT, result TEXT)""")
conn.commit()

# --- DMM connection ---
rm = pyvisa.ResourceManager()
dmm = rm.open_resource(DMM_VISA)
dmm.write_termination = dmm.read_termination = "\n"

# --- Graceful stop ---
running = True
def stop(sig, frame):  # Stop loop on Ctrl-C
    global running; running = False
signal.signal(signal.SIGINT, stop)

# --- GUI setup ---
root = Tk(); root.title("DMM Reader")
reading_var = StringVar(); result_var = StringVar()
Label(root, text="DMM Reading:", font=("Arial", 14)).pack()
Label(root, textvariable=reading_var, font=("Arial", 18)).pack()
Label(root, textvariable=result_var, font=("Arial", 16)).pack()

def get_reading():
    """Query DMM and return value, unit, function."""
    func = dmm.query("FUNC?").strip().replace('"','')
    val = float(dmm.query("READ?").strip())
    unit = func.split(":")[0].upper()
    return val, unit, func

def poll():
    """Poll DMM, update GUI, and log to DB."""
    if running:
        val, unit, func = get_reading()
        now = dt.datetime.utcnow().isoformat(timespec="seconds")
        # Determine pass/fail
        result = "PASSED" if 5 <= val <= 10 else "Failed"
        # Update GUI
        reading_var.set(f"{val:+.6f} {unit} ({func})")
        result_var.set(result)
        # Log to DB
        cur.execute(f"INSERT INTO {TABLE} (utc,value,unit,function,result) VALUES (?,?,?,?,?)",
                    (now, val, unit, func, result))
        conn.commit()
        # Schedule next poll
        root.after(int(POLL_SEC * 1000), poll)
    else:
        # On exit, close resources
        conn.close(); dmm.close(); root.destroy(); sys.exit(0)

# --- Start polling and GUI loop ---
poll()
root.mainloop()
