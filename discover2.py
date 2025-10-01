#!/usr/bin/env python3
"""
Live DMM logger → SQLite
Author: you
"""
import pyvisa
import sqlite3
import datetime as dt
import time
import signal
import sys
import os

DB_FILE   = "dmm_log.db"
TABLE     = "readings"
DMM_VISA  = "USB0::0x2A8D::0x1701::MY57102012::INSTR"
POLL_SEC  = 1.0

# ---------- SQL schema --------------------------------------------
CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    utc       TEXT NOT NULL,
    value     REAL NOT NULL,
    unit      TEXT NOT NULL,
    function  TEXT NOT NULL
);
"""

# ---------- graceful stop -----------------------------------------
running = True
def stop(sig, frame):
    global running
    running = False
signal.signal(signal.SIGINT, stop)

# ---------- connect DMM -------------------------------------------
rm  = pyvisa.ResourceManager()
dmm = rm.open_resource(DMM_VISA)
dmm.write_termination = dmm.read_termination = "\n"
print("DMM:", dmm.query("*IDN?").strip())

# ---------- open DB -----------------------------------------------
conn = sqlite3.connect(DB_FILE, isolation_level=None)  # autocommit off
cur  = conn.cursor()
cur.execute(CREATE_SQL)
conn.commit()

# ---------- helper -------------------------------------------------
def get_reading():
    """Return (value, unit, function) tuple."""
    func = dmm.query("FUNC?").strip().replace('"','')  # "VOLT:DC"
    raw  = dmm.query("READ?").strip()                  # e.g. +1.23456789E+00
    val  = float(raw)
    unit = func.split(":")[0].upper()                  # VOLT → V, CURR → A …
    return val, unit, func

# ---------- main loop ---------------------------------------------
print(f"Logging every {POLL_SEC} s …  Ctrl-C to stop")
try:
    while running:
        val, unit, func = get_reading()
        now = dt.datetime.utcnow().isoformat(timespec="seconds")
        cur.execute(f"INSERT INTO {TABLE} (utc,value,unit,function) VALUES (?,?,?,?)",
                    (now, val, unit, func))
        conn.commit()
        print(f"{now}  {val:+.6f} {unit}", end="\r")
        # Value check and print result
        if val <= 5:
            print("Failed")
        elif 5 <= val <= 10:
            print("PASSED")
        time.sleep(POLL_SEC)
except Exception as e:
    print("\nError:", e)
finally:
    print("\nShutting down …")
    conn.close()
    dmm.close()
    sys.exit(0)

# Display the absolute path of the database and list its tables
print("DB absolute path:", os.path.abspath(DB_FILE))
conn = sqlite3.connect(DB_FILE)
print("Tables:", conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
conn.close()