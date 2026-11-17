"""Remove test/demo rows from the dashboard so only real sends show."""
import sqlite3

TEST_ADDRS = ("selftest@probe.io", "x@y.com", "hr@bigcorp.com",
              "client@testcompany.com", "me@personal-mail.com",
              "client@startup.io", "founder@ycombinator.com")

conn = sqlite3.connect("tracker.db")
qmarks = ",".join("?" * len(TEST_ADDRS))
inner = f"SELECT id FROM tracked WHERE recipient IN ({qmarks})"
conn.execute(f"DELETE FROM events WHERE tracked_id IN ({inner})", TEST_ADDRS)
conn.execute(f"DELETE FROM tracked WHERE recipient IN ({qmarks})", TEST_ADDRS)
conn.commit()
print("remaining tracked:", conn.execute("SELECT COUNT(*) FROM tracked").fetchone()[0])
