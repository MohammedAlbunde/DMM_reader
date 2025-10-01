import sqlite3

DB_FILE = "dmm_log.db"
TABLE = "readings"

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()
try:
    cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN result TEXT;")
    print("Column added.")
except sqlite3.OperationalError as e:
    print("Column may already exist:", e)
conn.commit()
conn.close()