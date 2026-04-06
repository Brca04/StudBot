# Made by Brca04

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
import sys
import signal
from datetime import datetime

# Your Discord webhook URL
DISCORD_WEBHOOK_URL = ""

# Target URL (Zagreb jobs)
URL = "https://studentski-poslovi.hr/pretraga?category=sve-kategorije&location=315&radius=10&activated_from=all&min_hour_rate="

HEADERS = {"User-Agent": "Mozilla/5.0"}
MESSAGE_IDS_FILE = "message_ids.json"

def signal_handler(sig, frame):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Ctrl+C pressed. Exiting.")
    sys.exit(0)

def load_previous():
    if os.path.exists("jobs.json"):
        with open("jobs.json", "r") as f:
            return json.load(f)
    return []

def save_current(jobs):
    with open("jobs.json", "w") as f:
        json.dump(jobs, f)

def load_message_ids():
    if os.path.exists(MESSAGE_IDS_FILE):
        with open(MESSAGE_IDS_FILE, "r") as f:
            return json.load(f)
    return []

def save_message_ids(ids):
    with open(MESSAGE_IDS_FILE, "w") as f:
        json.dump(ids, f)

def delete_previous_messages():
    msg_ids = load_message_ids()
    for msg_id in msg_ids:
        try:
            url = f"{DISCORD_WEBHOOK_URL}/messages/{msg_id}"
            r = requests.delete(url)
            if r.status_code == 204:
                print(f"  🗑️ Deleted message {msg_id}")
            time.sleep(0.5)
        except:
            pass
    save_message_ids([])

def fetch_listings(URL):
    response = requests.get(URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")
    listings = []

    for job_div in soup.find_all("div", dusk=re.compile(r"^job-\d+$")):
        a_tag = job_div.find("a", href=True)
        link = a_tag["href"].strip() if a_tag else ""

        title_tag = job_div.find("h5", attrs={"dusk": True})
        price_tag = job_div.find("span", class_="inline-block me-1 text-slate-600")
        date_tag = job_div.find("span", class_="block text-sm text-slate-600")

        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        pay = " ".join(price_tag.get_text().split()) if price_tag else "N/A"
        date = date_tag.get_text(strip=True) if date_tag else ""

        listings.append({
            "title": title,
            "link": link,
            "pay": pay,
            "date": date
        })

    return listings

def parse_pay(pay_str):
    try:
        return float(pay_str.split()[0].replace(",", "."))
    except:
        return 0.0

def rate_job(pay_value):
    if pay_value > 10.0:
        return "purple"
    elif pay_value >= 8.0:
        return "green"
    elif pay_value > 0:
        return "red"
    return "unknown"

def send_discord_notification(new_jobs):
    if not new_jobs:
        return

    header = "**@everyone 🆕 Novi studentski poslovi pronađeni!**\n\n"
    chunks = [header]

    for job in new_jobs:
        pay_value = parse_pay(job["pay"])
        rating = rate_job(pay_value)
        date_str = f" · {job['date']}" if job.get("date") else ""

        if rating == "purple":
            entry = f"🟣 [{job['title']}](<{job['link']}>){date_str}\n```md\n# {job['pay']}\n```\n"
        elif rating == "green":
            entry = f"🟢 [{job['title']}](<{job['link']}>){date_str}\n```diff\n+ {job['pay']}\n```\n"
        elif rating == "red":
            entry = f"🔴 [{job['title']}](<{job['link']}>){date_str}\n```diff\n- {job['pay']}\n```\n"
        else:
            continue

        if len(chunks[-1]) + len(entry) > 2000:
            chunks.append("")
        chunks[-1] += entry

    sent_ids = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk}, params={"wait": "true"})
        if response.status_code == 200:
            msg_id = response.json().get("id")
            if msg_id:
                sent_ids.append(msg_id)
            print(f"  ✅ Sent to Discord.")
        else:
            print(f"  ⚠️ Discord error: {response.status_code}")

    save_message_ids(sent_ids)

def main():
    ts = datetime.now().strftime("%H:%M:%S")
    current = []
    for page in range(1, 6):
        page_url = f"{URL}&page={page}"
        page_listings = fetch_listings(page_url)
        if not page_listings:
            break
        current.extend(page_listings)

    previous = load_previous()
    previous_titles = {job["title"] for job in previous}
    new_jobs = [job for job in current if job["title"] not in previous_titles]

    if new_jobs:
        print(f"[{ts}] 🚨 {len(new_jobs)} new listing(s) found!")
        for job in new_jobs:
            print(f"  → {job['title']} | {job['pay']}")
        delete_previous_messages()
        send_discord_notification(new_jobs)
        save_current(current)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            main()
            time.sleep(60)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Error: {e}")
            time.sleep(60)
