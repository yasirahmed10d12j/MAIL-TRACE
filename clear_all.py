"""Wipe ALL tracked emails + events from the dashboard (fresh start)."""
import sqlite3

conn = sqlite3.connect("tracker.db")
conn.execute("DELETE FROM events")
conn.execute("DELETE FROM tracked")
conn.commit()
print("cleared — remaining tracked:", conn.execute("SELECT COUNT(*) FROM tracked").fetchone()[0])
