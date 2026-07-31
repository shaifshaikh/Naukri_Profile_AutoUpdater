# 🚀 Naukri Profile Auto-Updater

Automatically keeps your Naukri.com profile "fresh" and visible to recruiters by periodically:

1. **Toggling your display name** — adds/removes a trailing `.` to trigger a profile update
2. **Uploading a dated resume** — copies your resume with today's date appended and uploads it

---

## 📋 Prerequisites

- **Python 3.9+** — [Download here](https://www.python.org/downloads/)
- **Google Chrome** — installed and logged into your Naukri account
- **pip** — comes with Python

---

## ⚡ Quick Start

### Option A: Run as Python script

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Edit config.json (see Configuration below)

# 3. IMPORTANT: Close Chrome completely!

# 4. Run
python naukri_updater.py
```

### Option B: Build standalone EXE

```bash
# 1. Double-click build_exe.bat (or run from terminal)
build_exe.bat

# 2. Edit dist\config.json

# 3. IMPORTANT: Close Chrome completely!

# 4. Run dist\NaukriUpdater.exe
```

---

## ⚙️ Configuration

Edit `config.json` before running:

```json
{
    "update_interval_minutes": 240,
    "resume_path": "C:\\Users\\YourName\\Documents\\MyResume.pdf",
    "chrome_user_data_dir": "C:\\Users\\YourName\\AppData\\Local\\Google\\Chrome\\User Data",
    "chrome_profile": "Default",
    "headless": false,
    "max_retries": 3,
    "retry_delay_seconds": 5,
    "screenshot_on_failure": true,
    "log_file": "naukri_updater.log"
}
```

| Setting | Description | Default |
|---------|-------------|---------|
| `update_interval_minutes` | How often to update (in minutes) | `240` (4 hours) |
| `resume_path` | Full path to your resume file (.pdf/.doc/.docx) | — |
| `chrome_user_data_dir` | Chrome user data directory | `C:\Users\<you>\AppData\Local\Google\Chrome\User Data` |
| `chrome_profile` | Chrome profile folder name | `Default` |
| `headless` | Run Chrome in background (no visible window) | `false` |
| `max_retries` | Retry attempts per update cycle | `3` |
| `retry_delay_seconds` | Seconds between retries | `5` |
| `screenshot_on_failure` | Save screenshots on errors | `true` |
| `log_file` | Log file name | `naukri_updater.log` |

### Finding your Chrome Profile

1. Open Chrome
2. Type `chrome://version` in the address bar
3. Look for **Profile Path** — the parent folder is your `chrome_user_data_dir`, and the last folder name is your `chrome_profile`

Example:
- Profile Path: `C:\Users\shaik\AppData\Local\Google\Chrome\User Data\Default`
- `chrome_user_data_dir` = `C:\Users\shaik\AppData\Local\Google\Chrome\User Data`
- `chrome_profile` = `Default`

---

## ⚠️ Important Notes

1. **Close Chrome before running** — Selenium needs exclusive access to your Chrome profile. If Chrome is already open, the app will fail to launch.

2. **Stay logged in** — The app uses your existing Chrome session. Log into Naukri in Chrome first, then close Chrome, then run this app.

3. **Firewall/Antivirus** — Some antivirus may flag PyInstaller executables. Add an exception if needed.

4. **Resume file** — Your original resume is never modified. A dated copy is created in the `dated_resumes/` folder.

---

## 📁 Project Structure

```
Naukri_App/
├── config.json           # Your configuration (edit this!)
├── naukri_updater.py      # Main Python script
├── requirements.txt       # Python dependencies
├── build_exe.bat          # One-click EXE builder
├── README.md              # This file
├── naukri_updater.log     # Log file (created on run)
├── screenshots/           # Debug screenshots (created on failure)
└── dated_resumes/         # Dated resume copies (created on run)
```

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| "Chrome is being controlled by automated software" | Normal — this is Selenium. Your session is still valid. |
| "Not logged in" | Close app → Open Chrome → Log into Naukri → Close Chrome → Restart app |
| "ChromeDriver version mismatch" | Delete `~/.wdm` folder and retry — it will auto-download the correct version |
| Name edit not working | Naukri may have changed their UI — check `screenshots/` for debug info |
| EXE flagged by antivirus | Add `dist/NaukriUpdater.exe` to your antivirus exceptions |

---

## 📜 License

Personal use only. Use responsibly and in accordance with Naukri's Terms of Service.
