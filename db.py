import sqlite3

DB_PATH = "hospital.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            phone TEXT,
            doctor TEXT NOT NULL,
            appointment_datetime TEXT NOT NULL,   -- 'YYYY-MM-DD HH:MM'
            status TEXT NOT NULL DEFAULT 'scheduled',
            reminder_sent INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_doctor_slot
        ON appointments(doctor, appointment_datetime)
        WHERE status = 'scheduled'
    """)
    conn.commit()
    conn.close()