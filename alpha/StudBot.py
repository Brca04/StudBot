# Made by Brca04

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
import sys
import signal
import shutil
from datetime import datetime, timedelta

BACKUP_INTERVAL_SECONDS = 3600  # 1 hour

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

def backup_if_stale():
    """Copy jobs.json -> backup.json if the backup is missing or older than BACKUP_INTERVAL_SECONDS."""
    if not os.path.exists("jobs.json"):
        return
    if os.path.exists("backup.json"):
        age = time.time() - os.path.getmtime("backup.json")
        if age < BACKUP_INTERVAL_SECONDS:
            return
    shutil.copy2("jobs.json", "backup.json")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Backup written (backup.json)")

def delete_webhook_message(webhook_url, message_id):
    try:
        r = requests.delete(f"{webhook_url}/messages/{message_id}", timeout=10)
        return r.status_code in (200, 204)
    except:
        return False

def cleanup_old_jobs(jobs):
    now = datetime.now()
    ts = now.strftime('%H:%M:%S')
    kept = []
    removed = 0
    for j in jobs:
        expires = j.get("expires", "")
        still_valid = False
        if expires:
            try:
                still_valid = datetime.fromisoformat(expires) > now
            except ValueError:
                still_valid = True  # unparseable — keep rather than drop
        else:
            still_valid = True

        if still_valid:
            kept.append(j)
            continue

        title = (j.get("title") or "?")[:60]
        msg_id = j.get("message_id")
        webhook = WEBHOOKS.get(j.get("tier"))
        if msg_id and webhook:
            if delete_webhook_message(webhook, msg_id):
                print(f"[{ts}] Deleted Discord msg [{j.get('tier')}] — {title}")
            else:
                print(f"[{ts}] FAILED to delete Discord msg [{j.get('tier')}] — {title}")
        else:
            print(f"[{ts}] Expired (no msg to delete) — {title}")
        removed += 1

    if removed:
        print(f"[{ts}] Removed {removed} expired job(s)")
    return kept

def fetch_job_dates(job_url):
    """Scrape publish date (Datum objave) and expiry (Oglas vrijedi do) from detail page."""
    try:
        response = requests.get(job_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")

        publish = ""
        expires = ""

        for p_tag in soup.find_all("p", class_="font-medium"):
            if "Datum objave" in p_tag.get_text():
                date_span = p_tag.find_next("span")
                if date_span:
                    publish = date_span.get_text(strip=True)
                break

        for node in soup.find_all(string=re.compile(r"Oglas vrijedi do", re.I)):
            parent = node.parent if node.parent else None
            haystack = parent.get_text(" ", strip=True) if parent else str(node)
            m = re.search(r"\d{1,2}\.\d{1,2}\.\d{4}\.?(?:\s*\d{1,2}:\d{2})?", haystack)
            if m:
                expires = m.group(0)
                break

        return publish, expires
    except:
        return "", ""

def parse_date_string(date_str):
    """Parse 'dd.mm.yyyy.' or 'dd.mm.yyyy. HH:MM' to datetime. Returns None on failure."""
    s = re.sub(r"(\d{4})\.\s", r"\1 ", date_str.strip()).rstrip(".")
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

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
    """Fetch publish + expiry dates from detail pages. Skips jobs already past expiry."""
    enriched = []
    for job in jobs:
        publish_str, expires_str = fetch_job_dates(job["link"])
        now = datetime.now()

        posted = parse_date_string(publish_str) if publish_str else None
        if posted:
            job["date"] = publish_str
            job["posted_iso"] = posted.isoformat()
        else:
            job["date"] = now.strftime("%d.%m.%Y.")
            job["posted_iso"] = now.isoformat()

        expires_dt = parse_date_string(expires_str) if expires_str else None
        if expires_dt and expires_dt <= now:
            # Site still lists a job past its own 'Oglas vrijedi do' — skip so we don't loop.
            time.sleep(0.3)
            continue
        job["expires"] = expires_dt.isoformat() if expires_dt else (now + timedelta(days=30)).isoformat()

        enriched.append(job)
        time.sleep(0.3)
    return enriched

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
    """Send each job as its own message so we can delete it later when it expires."""
    ts = datetime.now().strftime('%H:%M:%S')
    for job in sort_jobs(jobs):
        content = f"**{job['pay']}** — [{job['title']}](<{job['link']}>) - {job['date']}"
        try:
            r = requests.post(f"{webhook_url}?wait=true", json={"content": content}, timeout=10)
            if r.status_code in (200, 204):
                data = r.json()
                job["message_id"] = data.get("id", "")
                job["tier"] = tier_name
            else:
                print(f"[{ts}] Webhook post {r.status_code} for: {job.get('title','?')[:60]}")
        except Exception as e:
            print(f"[{ts}] Webhook error: {e}")
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

    previous_links = {job.get("link") for job in previous if job.get("link")}
    new_jobs = [job for job in current if job.get("link") and job["link"] not in previous_links]

    if new_jobs:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {len(new_jobs)} new job(s) found, fetching...")
        new_jobs = enrich_with_dates(new_jobs)
        send_discord_notification(new_jobs)

    all_jobs = previous + new_jobs
    save_current(all_jobs)
    backup_if_stale()

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
