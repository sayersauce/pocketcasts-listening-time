import time
import requests
import sqlite3
import os
from fastapi import FastAPI
from fastapi import Request
from fastapi.templating import Jinja2Templates

EMAIL = os.environ.get("EMAIL")
PASSWORD = os.environ.get("PASSWORD")
AUTH_URL = "https://api.pocketcasts.com/user/login"
SECONDS_URL = "https://api.pocketcasts.com/user/stats/summary"
# DB_PATH = "listening_time.db"
DB_PATH = "/data/db.sqlite3"
POLL_COOLDOWN = 300
last_poll_time = 0

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS listening_time (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            seconds INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_seconds(timestamp, seconds):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO listening_time (timestamp, seconds) VALUES (?, ?)",
        (timestamp, seconds)
    )
    conn.commit()
    conn.close()

def poll_api():
    try:
        auth_response = requests.post(AUTH_URL, json={"email": EMAIL, "password": PASSWORD})
        auth_response.raise_for_status()
        token = auth_response.json().get("token")

        if not token:
            print("Authentication failed, no token received.")
            return None

        seconds_response = requests.post(SECONDS_URL, headers={"Authorization": f"Bearer {token}"})
        seconds_response.raise_for_status()
        latest_data = {
            "status": seconds_response.status_code,
            "response": seconds_response.json(),
            "timestamp": time.time()
        }

        print(f"Data polled successfully at {time.ctime(latest_data['timestamp'])}")

        return latest_data
    except requests.RequestException as e:
        print(f"Request failed: {e}")
    except Exception as e:
        print(f"Error polling API: {e}")
    return None

def response_to_seconds(response):
    silence = int(response.get("timeSilenceRemoval") or 0)
    skipping = int(response.get("timeSkipping") or 0)
    intro_skipping = int(response.get("timeIntroSkipping") or 0)
    variable_speed = int(response.get("timeVariableSpeed") or 0)
    listened = int(response.get("timeListened") or 0)

    return listened - (silence + skipping + intro_skipping + variable_speed)

app = FastAPI()
templates = Jinja2Templates(directory=".")

@app.get("/")
def root(request: Request):
    global last_poll_time

    if time.time() - last_poll_time > POLL_COOLDOWN:
        data = poll_api()
        if data and data['response']:
            seconds = response_to_seconds(data['response'])
            save_seconds(data['timestamp'], seconds)
        last_poll_time = time.time()
    else:
        print("Skipping API poll due to cooldown.")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, seconds FROM listening_time WHERE timestamp >= ?", (time.time() - 7*24*3600,))
    history = c.fetchall()
    conn.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "seconds": history[-1][1] if history else 0,
        "history": history
    })

init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
