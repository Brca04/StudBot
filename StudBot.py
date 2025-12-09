# Made by Brca04

import requests
from bs4 import BeautifulSoup
import json
import time
import os
import sys
import signal

# Your Discord webhook URL
DISCORD_WEBHOOK_URL = ""

# Target URL (Zagreb jobs)
URL = "https://studentski-poslovi.hr/pretraga?category=sve-kategorije&province=zagreb&activated_from=all"

# Alternative URL for Page Iteration
#URL = "https://studentski-poslovi.hr/pretraga?category=sve-kategorije&province=zagreb&search=Pretra%C5%BEi%20poslove&page=1"

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
def fetch_listings():
    response = requests.get(URL, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")
    listings = []

    for job_div in soup.find_all("div", attrs={"data-url": True}):
        link = job_div["data-url"].strip()

        title_tag = job_div.find("h5", attrs={"dusk": True})
        price_tag = job_div.find("span", class_="inline-block me-1 text-slate-600")

        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        pay = price_tag.get_text(strip=True) if price_tag else "N/A"

        listings.append({
            "title": title,
            "link": link,
            "pay": pay
        })

    return listings

# Notify Discord
def send_discord_notification(new_jobs):
    if not new_jobs:
        return

    content = "**@everyone 🆕 Novi studentski poslovi pronađeni!**\n"

    for job in new_jobs:
        # Parse pay string to float (e.g. "8.00 €" → 8.0)
        try:
            pay_value = float(job["pay"].split()[0].replace(",", "."))
        except:
            pay_value = 0.0

        # Choose Discord code block style based on pay
        if pay_value > 9.99:
            content += f"• [{job['title']}](<{job['link']}>)\n```md\n#{job['pay']}\n```\n"
        elif pay_value > 7.99 and pay_value < 10:
            content += f"• [{job['title']}](<{job['link']}>)\n```diff\n+{job['pay']}\n```\n"
        elif pay_value > 6.05 and pay_value < 8:
            content += f"• [{job['title']}](<{job['link']}>)\n```diff\n-{job['pay']}\n```\n"
        

    payload = {"content": content}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)

    if response.status_code == 204:
        print("✅ Sent to Discord.")
    else:
        print(f"⚠️ Discord error: {response.status_code} - {response.text}")

# Main
def main():
    print("\n🔎 Checking for new job listings...")
    current = fetch_listings()
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
