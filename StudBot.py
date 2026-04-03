# Made by Brca04

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
import sys
import signal

# Your Discord webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1397510612648591433/EGIVkncM3-JbmaE8ITbAsbGVy9y4lm_JmB0pT_hkFrJ10cfisQ4YzC0V2uiYvYOF29eh"

# Target URL (Zagreb jobs)
URL = "https://studentski-poslovi.hr/pretraga?category=sve-kategorije&location=315&radius=10&activated_from=all&min_hour_rate="


HEADERS = {"User-Agent": "Mozilla/5.0"}

# Handle Ctrl+C gracefully
def signal_handler(sig, frame):
    print("\n Ctrl+C pressed. Exiting.")
    sys.exit(0)

# Load previously seen jobs
def load_previous():
    if os.path.exists("jobs.json"):
        with open("jobs.json", "r") as f:
            return json.load(f)
    return []

# Save current job state
def save_current(jobs):
    with open("jobs.json", "w") as f:
        json.dump(jobs, f)

# Scrape jobs from the site
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

# Notify Discord
def send_discord_notification(new_jobs):
    if not new_jobs:
        return

    header = "**@everyone 🆕 Novi studentski poslovi pronađeni!**\n"
    chunks = [header]

    for job in new_jobs:
        try:
            pay_value = float(job["pay"].split()[0].replace(",", "."))
        except:
            pay_value = 0.0

        date_str = f" · {job['date']}" if job.get("date") else ""
        if pay_value > 9.99:
            entry = f"• [{job['title']}](<{job['link']}>){date_str}\n```md\n# {job['pay']}\n```\n"
        elif pay_value > 7.99:
            entry = f"• [{job['title']}](<{job['link']}>){date_str}\n```diff\n+ {job['pay']}\n```\n"
        elif pay_value > 6.05:
            entry = f"• [{job['title']}](<{job['link']}>){date_str}\n```diff\n- {job['pay']}\n```\n"
        else:
            continue

        if len(chunks[-1]) + len(entry) > 2000:
            chunks.append("")
        chunks[-1] += entry

    for chunk in chunks:
        if not chunk.strip():
            continue
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": chunk})
        if response.status_code == 204:
            print("✅ Sent to Discord.")
        else:
            print(f"⚠️ Discord error: {response.status_code} - {response.text}")

# Main
def main():
    print("\n🔎 Checking for new job listings...")
    current = []
    for page in range(1, 6):  # Check first 5 pages
        page_url = f"{URL}&page={page}"
        page_listings = fetch_listings(page_url)
        if not page_listings:
            break
        current.extend(page_listings)

    previous = load_previous()
    previous_titles = {job["title"] for job in previous}
    new_jobs = [job for job in current if job["title"] not in previous_titles]

    if new_jobs:
        print(f"🚨 Found {len(new_jobs)} new listing(s). Sending to Discord...")
        send_discord_notification(new_jobs)
        save_current(current)
    else:
        print("✅ No new listings.")

# Auto-loop every 60 seconds
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            main()
            print("⏳ Next check in 60 seconds...")
            for i in range(60):
                time.sleep(1)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            for i in range(60):
                time.sleep(1)
