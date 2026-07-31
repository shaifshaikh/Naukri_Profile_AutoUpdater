# Naukri_Profile_AutoUpdater
Automates keeping your Naukri.com profile "active" by periodically toggling your display name and re-uploading a freshly dated copy of your resume, using Selenium. Runs once (Task Scheduler) or continuously (internal scheduler).


# Naukri Profile Auto-Updater

A Selenium-based automation tool that keeps your Naukri.com profile
looking freshly updated to recruiters — without you having to log in
and manually touch it every few hours.

## What it does

Naukri ranks/surfaces profiles partly based on recency of activity.
This tool triggers a genuine profile update on a schedule by:

1. **Toggling your display name** — appends/removes a trailing `.`
   on your profile name and saves, which updates your "last modified"
   timestamp.
2. **Re-uploading your resume** — creates a same-folder, dated copy
   of your resume (e.g. `Resume_31072026.pdf`) and uploads it, which
   refreshes the "Uploaded on" date shown to recruiters.

Both actions run through a real Chrome browser session via Selenium,
using your existing logged-in profile — no credentials are stored or
automated at the login step; first-time login is manual, then the
session persists.

## Features

- Works with Chrome (Brave/Edge configurable)
- `--once` mode for Windows Task Scheduler, or `--loop` mode for a
  built-in scheduler
- Configurable update interval, retry logic, and headless mode
- Colored console + file logging, with screenshots on failure
- Resume renaming avoids duplicate/stacked-date files on reruns

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `config.json.example` to `config.json` and fill in your
   resume path and browser profile details
3. Run: `python naukri_updater.py --once` (or `--loop`)

## Disclaimer

This is a personal automation tool for your own Naukri account.
Use responsibly and in line with Naukri's terms of service.



## Need Open Source Contributors for the below task
For the future scope of this solution, the system can be enhanced to include an automated job discovery and application mechanism. This would involve integrating with Neo AI APIs to periodically check for relevant job openings based on predefined criteria such as role (e.g., .NET Developer, MVC, .NET Core) and preferred locations (Mumbai, Andheri, Airoli, Thane, etc.). The system can intelligently parse resume data and Naukri profile details to auto-fill application forms and respond to standard screening questions (such as willingness to relocate, years of experience, and other basic eligibility criteria). Additionally, location-based filtering can be applied to ensure that only jobs within preferred locations are marked positively. Once suitable jobs are identified, the system can automatically apply to them while maintaining a log of applications submitted. This enhancement would significantly reduce manual effort and improve efficiency in job search and application processes. Further implementation details, including API endpoint access and integration workflow for Neo AI, can be incorporated based on shared documentation.

