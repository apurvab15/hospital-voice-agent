import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from db import get_db

HOSPITAL_TZ = ZoneInfo("America/Chicago")   # set this to the hospital's time zone
RETELL_URL = "https://api.retellai.com/v2/create-phone-call"

def send_reminders():
    api_key = os.getenv("RETELL_API_KEY")
    from_number = os.getenv("RETELL_FROM_NUMBER")
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    tomorrow = (datetime.now(HOSPITAL_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")

    conn = get_db()
    rows = conn.execute(
        """SELECT id, patient_name, phone, doctor, appointment_datetime
           FROM appointments
           WHERE date(appointment_datetime) = ?
             AND status = 'scheduled'
             AND reminder_sent = 0
             AND phone IS NOT NULL""",
        (tomorrow,),
    ).fetchall()

    sent, failed = 0, 0
    for r in rows:
        payload = {
            "from_number": from_number,
            "to_number": r["phone"],
            "retell_llm_dynamic_variables": {
                "patient_name": r["patient_name"],
                "doctor": r["doctor"],
                "appointment_time": r["appointment_datetime"],
            },
            "metadata": {"appointment_id": r["id"], "type": "reminder"},
        }

        if dry_run:
            print("[DRY RUN] would call:", payload)
            continue

        try:
            resp = requests.post(
                RETELL_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            failed += 1
            print(f"Reminder failed for appointment {r['id']}: {e}")
            continue

        conn.execute("UPDATE appointments SET reminder_sent = 1 WHERE id = ?", (r["id"],))
        conn.commit()
        sent += 1

    conn.close()
    return {"tomorrow": tomorrow, "matched": len(rows), "sent": sent,
            "failed": failed, "dry_run": dry_run}