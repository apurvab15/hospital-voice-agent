import sqlite3
import json
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import requests
from datetime import datetime, timedelta
from db import get_db


RETELL_URL = "https://api.retellai.com/v2/create-phone-call"

from db import get_db, init_db
from reminders import send_reminders, HOSPITAL_TZ
from retell import Retell

scheduler = BackgroundScheduler(timezone=HOSPITAL_TZ)
retell = Retell(api_key=os.environ["RETELL_API_KEY"])



@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

async def verify_and_parse(request : Request):
    raw_body = (await request.body()).decode("utf-8")
    content = json.loads(raw_body)

    print("=== Incoming request ===")
    print(json.dumps(content.get("args",{}), indent=2))
    print("========================")
    
    valid = retell.verify(
        raw_body, 
        api_key=os.environ["RETELL_API_KEY"],
        signature=request.headers.get("X-Retell-Signature")
    )
    if not valid:
        return None
    
   
    return content

@app.get("/")
async def welcome():
    return HTMLResponse("<h1>Welcome to Retell Medical Clinic!</h1>")


@app.get("/check-availability")
async def check_availability():
    
    print("Checking Avaliblilty")
    
    return JSONResponse(status_code=200, content={
        "status": "success",
        "available": True,
        "hours": "9:00 AM - 5:00 PM",
        "days": "every day"
    })

@app.post("/book-appointment")
async def book_appointment(request : Request):
    content = await verify_and_parse(request)

    if content is None :
        return JSONResponse(status_code=401,content={ "message" : "Unauthorized"})
    
    
    args = content.get("args", {})
    name = (args.get("patient_name") or "").strip()
    doctor = (args.get("doctor") or "").strip()
    time = (args.get("time") or "").strip()
    date = (args.get("date") or "").strip()
    phone = (args.get("phone")  or "").strip()
    
    print(name, doctor, date, time)

    if not (name and date and time):
        return JSONResponse(status_code=404, content={ 
            "message": "Missing name, doctor or appointment time"
        })
    
    """
    try:
        dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return {"result": "I couldn't understand that date and time. Could you say it again?"}

    if dt <= datetime.now(HOSPITAL_TZ).replace(tzinfo=None):
        return {"result": "That time has already passed. Could we pick a future time?"}
    """
    
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO appointments (patient_name, phone, doctor, date, time) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, phone, doctor, date, time),
        )
        conn.commit()
        appointment_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return {"result": f"Sorry, {doctor} is already booked at that time. Would you like a different time?"}
    finally:
        conn.close()

    return JSONResponse(status_code=200, content={
        "status": "success",
        "appointment_id": appointment_id,
        "patient_name": name,
        "doctor": doctor,
        "date": date,
        "time": time
    })

"""
@app.delete("/cancel_appointment")
def cancel_appointment(payload: RetellFunctionCall):
    args = payload
    name = 




@app.post("/jobs/send-reminders")
def run_reminders_now():
    return send_reminders()


"""