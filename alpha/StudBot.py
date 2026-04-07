# Made by Brca04

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
import sys
import signal
from datetime import datetime, timedelta

# Webhook per tier - each goes to its own channel
WEBHOOKS = {
    "purple": "",
    "green": "",
    "red": "",
}

# Target URL (Zagreb jobs)
URL = "https://studentski-poslovi.hr/pretraga?category=sve-kategorije&location=315&radius=10&activated_from=all&min_hour_rate="

HEADERS = {"User-Agent": "Mozilla/5.0"}

TIER_HEADERS = {
    "purple": "**Odlicno placeni (>10 eur/h)**",
    "green": "**Dobro placeni (8-10 eur/h)**",
    "red": "**Nisko placeni (<8 eur/h)**",
}

def signal_handler(sig, frame):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Exiting.")
    sys.exit(0)

def load_previous():
    if os.path.exists("jobs.json"):
        with open("jobs.json", "r") as f:
            return json.load(f)
    return []

def save_current(jobs):
    with open("jobs.json", "w") as f:
        json.dump(jobs, f)

def cleanup_old_jobs(jobs):
    now = datetime.now()
    before = len(jobs)
    kept = []
    for j in jobs:
        expires = j.get("expires", "")
        if expires:
            try:
                if datetime.fromisoformat(expires) > now:
                    kept.append(j)
            except:
                kept.append(j)
        else:
            kept.append(j)
    removed = before - len(kept)
    if removed > 0:
        print(f"[{now.strftime('%H:%M:%S')}] Removed {removed} expired job(s)")
    return kept

def fetch_publish_date(job_url):
    """Fetch the actual publish date (Datum objave) from a job's detail page."""
    try:
        response = requests.get(job_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        # Find "Datum objave:" label and get the date next to it
        for p_tag in soup.find_all("p", class_="font-medium"):
            if "Datum objave" in p_tag.get_text():
                date_span = p_tag.find_next("span")
                if date_span:
                    return date_span.get_text(strip=True)
        return ""
    except:
        return ""

def parse_date_string(date_str):
    """Parse dd.mm.yyyy. format to datetime."""
    try:
        clean = date_str.strip().rstrip(".")
        return datetime.strptime(clean, "%d.%m.%Y")
    except:
        return datetime.now()

def fetch_listings(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(response.text, "html.parser")
    listings = []

    for job_div in soup.find_all("div", dusk=re.compile(r"^job-\d+$")):
        a_tag = job_div.find("a", href=True)
        link = a_tag["href"].strip() if a_tag else ""

        title_tag = job_div.find("h5", attrs={"dusk": True})
        price_tag = job_div.find("span", class_="inline-block me-1 text-slate-600")

        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        pay = " ".join(price_tag.get_text().split()) if price_tag else "N/A"

        listings.append({
            "title": title,
            "link": link,
            "pay": pay,
            "date": "",
            "posted_iso": "",
            "expires": ""
        })

    return listings

def enrich_with_dates(jobs):
    """Fetch actual publish dates for new jobs from their detail pages."""
    for job in jobs:
        date_str = fetch_publish_date(job["link"])
        if date_str:
            job["date"] = date_str
            posted = parse_date_string(date_str)
            job["posted_iso"] = posted.isoformat()
            job["expires"] = (posted + timedelta(days=30)).isoformat()
        else:
            now = datetime.now()
            job["date"] = now.strftime("%d.%m.%Y.")
            job["posted_iso"] = now.isoformat()
            job["expires"] = (now + timedelta(days=30)).isoformat()
        time.sleep(0.3)  # Rate limit

def parse_pay(pay_str):
    try:
        return float(pay_str.split()[0].replace(",", "."))
    except:
        return 0.0

def get_tier(pay_value):
    if pay_value > 9.99:
        return "purple"
    elif pay_value > 7.99:
        return "green"
    elif pay_value > 6.05:
        return "red"
    return None

def sort_jobs(jobs):
    return sorted(jobs, key=lambda j: (parse_pay(j["pay"]), j.get("posted_iso", "")), reverse=True)

def send_to_webhook(webhook_url, jobs, tier_name):
    jobs = sort_jobs(jobs)

    header = f"{TIER_HEADERS[tier_name]} — {len(jobs)}\n\n"
    chunks = [header]

    for job in jobs:
        entry = f"**{job['pay']}** — [{job['title']}](<{job['link']}>) - {job['date']}\n"

        if len(chunks[-1]) + len(entry) > 1900:
            chunks.append(f"{TIER_HEADERS[tier_name]} (nastavak)\n\n")
        chunks[-1] += entry

    for chunk in chunks:
        requests.post(webhook_url, json={"content": chunk}, timeout=10)
        time.sleep(0.5)

def send_discord_notification(new_jobs):
    if not new_jobs:
        return

    tiers = {"purple": [], "green": [], "red": []}
    for job in new_jobs:
        tier = get_tier(parse_pay(job["pay"]))
        if tier:
            tiers[tier].append(job)

    for tier_name in ["purple", "green", "red"]:
        if not tiers[tier_name]:
            continue

        webhook = WEBHOOKS.get(tier_name)
        if not webhook:
            continue

        send_to_webhook(webhook, tiers[tier_name], tier_name)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sent {len(tiers[tier_name])} {tier_name} job(s)")

def main():
    current = []
    for page in range(1, 6):
        page_url = f"{URL}&page={page}"
        page_listings = fetch_listings(page_url)
        if not page_listings:
            break
        current.extend(page_listings)

    previous = load_previous()
    previous = cleanup_old_jobs(previous)

    previous_titles = {job["title"] for job in previous}
    new_jobs = [job for job in current if job["title"] not in previous_titles]

    if new_jobs:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(new_jobs)} new job(s) found, fetching...")
        enrich_with_dates(new_jobs)
        send_discord_notification(new_jobs)

    all_jobs = previous + new_jobs
    save_current(all_jobs)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] StudBot started")

    while True:
        try:
            main()
            time.sleep(60)
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
            time.sleep(60)
