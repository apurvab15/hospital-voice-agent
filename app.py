import sqlite3
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
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

from db import get_db, init_db
from schema import RetellFunctionCall
from reminders import send_reminders, HOSPITAL_TZ

scheduler = BackgroundScheduler(timezone=HOSPITAL_TZ)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(send_reminders, CronTrigger(hour=18, minute=0, timezone=HOSPITAL_TZ),
                      id="daily_reminders", replace_existing=True)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post("/functions/book_appointment")
def book_appointment(payload: RetellFunctionCall):
    args = payload.args
    name = (args.get("patient_name") or "").strip()
    doctor = (args.get("doctor") or "").strip()
    when = (args.get("appointment_datetime") or "").strip()
    phone = payload.call.get("from_number") or args.get("phone")

    if not (name and doctor and when):
        return {"result": "I still need the patient's name, the doctor, and the date and time."}

    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return {"result": "I couldn't understand that date and time. Could you say it again?"}

    if dt <= datetime.now(HOSPITAL_TZ).replace(tzinfo=None):
        return {"result": "That time has already passed. Could we pick a future time?"}

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO appointments (patient_name, phone, doctor, appointment_datetime) "
            "VALUES (?, ?, ?, ?)",
            (name, phone, doctor, when),
        )
        conn.commit()
        appointment_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return {"result": f"Sorry, {doctor} is already booked at that time. Would you like a different time?"}
    finally:
        conn.close()

    return {"result": f"You're booked with {doctor} on {dt.strftime('%A, %B %d at %I:%M %p')}. "
                      f"Your confirmation number is {appointment_id}."}

@app.post("/jobs/send-reminders")
def run_reminders_now():
    return send_reminders()