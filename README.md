# StudBot
StudBot is a web-scraping Discord bot that notifies you when new job listings are published on https://studentski-poslovi.hr/.  

## Features
- Bot checks for new jobs every minute
- When new job is found, bot sends a Discord message that includes basic information about the job
- Bot filters jobs and rates them based on the hourly wage into three tiers
- Each pay tier is sent to its own Discord channel via separate webhooks
- Jobs are sorted by pay (highest first), then by date (newest first)
- Scrapes actual publish date (Datum objave) from each job's detail page
- Automatically removes expired jobs from the database after 30 days
- Creates a local database in form of a json file

## Live Demo
You can join Discord server with working StudBot by clicking on this [link](https://discord.gg/NNfmUvty).

## Deployment
Currently running 24/7 on an Oracle Cloud free tier VM (VM.Standard.E2.1.Micro) as a systemd service.

## Compatibility
- Virtually anything that can run Python
- Tested on Oracle Cloud VM (Ubuntu 24.04), Raspberry Pi, and Windows