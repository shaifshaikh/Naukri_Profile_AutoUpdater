"""
+==============================================================+
|           NAUKRI PROFILE AUTO-UPDATER v2.2                   |
|  Keeps your Naukri profile active by periodically            |
|  toggling your display name and uploading a dated resume.    |
|                                                              |
|  Supports: Chrome / Brave / Edge (Chromium-based browsers)   |
|  Modes:  --once  (single run, for Task Scheduler)            |
|          --loop  (continuous, internal scheduler)             |
+==============================================================+

Author : Auto-generated
Usage  : python naukri_updater.py [--once | --loop]
Config : Edit config.json before first run

CHANGELOG (v2.2):
  - create_dated_resume(): FIXED. Now writes the dated copy into the SAME
    folder as the original resume (no more separate dated_resumes/ folder),
    and uses Naukri's actual filename convention DDMMYYYY with no
    separators (e.g. Shaif_Ahmed_Resume_31072026.pdf), matching what's
    confirmed in the "resume-name-inline" tile on the profile page.
  - create_dated_resume(): if resume_path in config.json already points at
    a previously-dated file (e.g. ..._30072026.pdf), the old _DDMMYYYY
    suffix is stripped before rebuilding the name for today, so re-runs
    don't stack dates (..._30072026_31072026.pdf) or silently reuse
    yesterday's file. It copies from the "clean" undated original if that
    still exists next to it, otherwise falls back to resume_path itself.
  - toggle_name() / update_resume(): removed unnecessary flat time.sleep()
    padding (the ~20s total came from stacked sleeps that weren't tied to
    actual page state). Replaced with explicit WebDriverWait conditions
    where possible:
      * the 2s "dialog opened" sleep is gone -- the next step already
        WebDriverWaits for the name input.
      * the 3s post-save sleep is now a WebDriverWait for the save modal
        to become invisible (falls back to a short 1s wait on timeout).
      * the 6s post-upload sleep is gone entirely -- it was redundant with
        the WebDriverWait(20) for the "Uploaded on" confirmation right
        after it.
      * small typing/click sleeps trimmed to the minimum needed for Naukri's
        JS to register input events.
"""

import argparse
import json
import os
import re
import sys
import shutil
import subprocess
import time
import logging
import traceback
from datetime import datetime
from pathlib import Path

import schedule
from colorama import init, Fore, Style
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

# ----------------------------------------------------------------
# Initialize colorama for Windows console colors
# ----------------------------------------------------------------
init(autoreset=True)

# Fix Windows console encoding -- force UTF-8
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_base_path():
    """Return the base path -- works both as script and as PyInstaller EXE."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()
CONFIG_PATH = os.path.join(BASE_PATH, "config.json")
SCREENSHOTS_DIR = os.path.join(BASE_PATH, "screenshots")
TOGGLE_STATE_FILE = os.path.join(BASE_PATH, ".toggle_state")


# ----------------------------------------------------------------
# Logging setup
# ----------------------------------------------------------------
def setup_logging(log_file: str):
    """Configure dual logging -- file + console with colors."""
    logger = logging.getLogger("NaukriUpdater")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fh = logging.FileHandler(os.path.join(BASE_PATH, log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(
        logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(ch)

    return logger


# ----------------------------------------------------------------
# Pretty console helpers
# ----------------------------------------------------------------
def banner():
    print(f"""
{Fore.CYAN}{Style.BRIGHT}
 +==============================================================+
 |         NAUKRI PROFILE AUTO-UPDATER  v2.2                    |
 +==============================================================+
 |  Keeps your profile fresh & visible to recruiters!           |
 |  Supports: Brave / Chrome / Edge                             |
 |  Press Ctrl+C to stop gracefully.                             |
 +==============================================================+
{Style.RESET_ALL}""")


def info(logger, msg):
    logger.info(f"{Fore.GREEN}[OK] {msg}{Style.RESET_ALL}")


def warn(logger, msg):
    logger.warning(f"{Fore.YELLOW}[WARN] {msg}{Style.RESET_ALL}")


def error(logger, msg):
    logger.error(f"{Fore.RED}[ERR] {msg}{Style.RESET_ALL}")


def step(logger, msg):
    logger.info(f"{Fore.CYAN}>> {msg}{Style.RESET_ALL}")


# ----------------------------------------------------------------
# Toggle state persistence (survives across --once runs)
# ----------------------------------------------------------------
def read_toggle_state() -> bool:
    try:
        if os.path.exists(TOGGLE_STATE_FILE):
            with open(TOGGLE_STATE_FILE, "r") as f:
                return f.read().strip() == "1"
    except Exception:
        pass
    return False


def write_toggle_state(has_dot: bool):
    try:
        with open(TOGGLE_STATE_FILE, "w") as f:
            f.write("1" if has_dot else "0")
    except Exception:
        pass


# ----------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------
def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        print(f"{Fore.RED}ERROR: config.json not found at {CONFIG_PATH}")
        print(f"{Fore.YELLOW}Please create config.json next to the executable.")
        input("Press Enter to exit...")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["resume_path", "browser_user_data_dir", "browser_profile"]
    for key in required:
        if key not in config or not config[key]:
            print(f"{Fore.RED}ERROR: '{key}' is missing or empty in config.json")
            input("Press Enter to exit...")
            sys.exit(1)

    config.setdefault("browser", "brave")
    config.setdefault("brave_binary_path",
                      r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
    config.setdefault("update_interval_minutes", 240)
    config.setdefault("headless", False)
    config.setdefault("max_retries", 3)
    config.setdefault("retry_delay_seconds", 5)
    config.setdefault("screenshot_on_failure", True)
    config.setdefault("log_file", "naukri_updater.log")

    return config


# ----------------------------------------------------------------
# Resume file helper
# ----------------------------------------------------------------
def create_dated_resume(original_path: str, logger: logging.Logger = None) -> str:
    """
    Return the path to today's dated resume copy, saved in the SAME folder
    as the original resume, using Naukri's DDMMYYYY naming (no separators)
    to match what actually shows up in the resume-name tile on the site.

    Behavior:
      - Strips any existing "_DDMMYYYY" suffix off the original file's stem
        first. This matters if resume_path in config.json already points at
        a previously-dated copy (e.g. left over from yesterday's run) --
        without this, the date would just keep stacking on the end.
      - If today's dated copy already exists, reuse that exact file.
      - Otherwise create a fresh dated copy. It copies from the "clean"
        undated file (e.g. Shaif_Ahmed_Resume.pdf) if that still exists in
        the same folder; otherwise it falls back to whatever
        resume_path pointed at.

    Examples:
      Shaif_Ahmed_Resume.pdf              -> Shaif_Ahmed_Resume_31072026.pdf
      Shaif_Ahmed_Resume_30072026.pdf     -> Shaif_Ahmed_Resume_31072026.pdf
    The original file is never modified or deleted.
    """
    original = Path(original_path)
    if not original.exists():
        raise FileNotFoundError(f"Resume file not found: {original_path}")

    today = datetime.now().strftime("%d%m%Y")

    # Strip a pre-existing _DDMMYYYY suffix so re-runs don't stack dates.
    base_stem = re.sub(r"_\d{8}$", "", original.stem)

    dated_name = f"{base_stem}_{today}{original.suffix}"
    dated_path = original.parent / dated_name

    if dated_path.exists():
        if logger:
            logger.debug(f"Today's dated resume already exists, reusing: {dated_name}")
        return str(dated_path)

    # Prefer copying from the clean/undated original if it's still there,
    # so we're always working from the true source file, not a stale dated
    # copy from a previous day.
    clean_original = original.parent / f"{base_stem}{original.suffix}"
    source = clean_original if clean_original.exists() else original

    shutil.copy2(str(source), str(dated_path))
    if logger:
        logger.debug(f"Created new dated resume for today: {dated_name} (from {source.name})")
    return str(dated_path)


# ----------------------------------------------------------------
# Main Updater Class
# ----------------------------------------------------------------
class NaukriUpdater:
    """Selenium-based Naukri.com profile updater -- works with Brave/Chrome/Edge."""

    NAUKRI_HOME = "https://www.naukri.com"
    NAUKRI_PROFILE = "https://www.naukri.com/mnjuser/profile"
    NAUKRI_LOGIN_PAGE = "https://www.naukri.com/nlogin/login"

    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.toggle_state = read_toggle_state()

    # -- Browser lifecycle

    @staticmethod
    def kill_browser_processes(browser_name="brave"):
        process_names = {
            "brave": "brave",
            "chrome": "chrome",
            "edge": "msedge",
        }
        proc_name = process_names.get(browser_name, browser_name)
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", f"{proc_name}.exe", "/T"],
                capture_output=True, text=True, timeout=15
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_browser(self):
        """Launch Chrome with a dedicated profile stored in the app folder."""
        step(self.logger, "Launching Chrome...")

        self.kill_browser_processes("chrome")
        time.sleep(2)

        profile_dir = os.path.join(BASE_PATH, "_naukri_chrome_profile")
        os.makedirs(profile_dir, exist_ok=True)

        options = Options()
        options.add_argument(f"--user-data-dir={profile_dir}")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--log-level=3")
        options.add_argument("--start-maximized")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)

        if self.config.get("headless"):
            options.add_argument("--headless=new")

        try:
            service = Service(ChromeDriverManager().install())
        except Exception as e:
            error(self.logger, f"ChromeDriver download failed: {e}")
            raise

        self.driver = webdriver.Chrome(service=service, options=options)

        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        info(self.logger, "Chrome launched successfully.")

    def close_browser(self):
        if self.driver:
            try:
                self.driver.quit()
                info(self.logger, "Browser closed.")
            except Exception:
                pass
            self.driver = None

    def take_screenshot(self, name: str):
        if not self.config.get("screenshot_on_failure"):
            return
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"{name}_{ts}.png")
        try:
            self.driver.save_screenshot(path)
            self.logger.debug(f"Screenshot saved: {path}")
        except Exception:
            pass

    # -- Login check

    def check_login(self) -> bool:
        step(self.logger, "Checking login status...")

        self.driver.get(self.NAUKRI_PROFILE)
        time.sleep(4)

        current_url = self.driver.current_url.lower()

        if "mnjuser/profile" in current_url and "login" not in current_url and "nlogin" not in current_url:
            info(self.logger, "Logged in to Naukri [YES]")
            return True

        warn(self.logger, "Not logged in -- currently on login page.")
        print(f"\n{Fore.YELLOW}{Style.BRIGHT}" + "=" * 60)
        print(f"  FIRST-TIME LOGIN REQUIRED")
        print(f"  Please log in to Naukri.com in the open Chrome window.")
        print(f"  The app will automatically continue once you submit login.")
        print("=" * 60 + f"{Style.RESET_ALL}\n")

        step(self.logger, "Waiting for manual login (up to 5 minutes)...")

        for i in range(100):
            time.sleep(3)
            sys.stdout.flush()
            try:
                cur_url = self.driver.current_url.lower()
                if "nlogin" not in cur_url and "login" not in cur_url:
                    step(self.logger, "Redirect detected! Verifying profile access...")
                    time.sleep(2)
                    self.driver.get(self.NAUKRI_PROFILE)
                    time.sleep(4)
                    verify_url = self.driver.current_url.lower()
                    if "mnjuser/profile" in verify_url and "login" not in verify_url and "nlogin" not in verify_url:
                        info(self.logger, "Logged in successfully! [YES]")
                        return True
            except Exception as e:
                self.logger.debug(f"Login poll error: {e}")

            if i > 0 and i % 10 == 0:
                step(self.logger, f"Still waiting for login... ({i*3}s elapsed)")
                sys.stdout.flush()

        error(self.logger, "Login timeout -- please try again.")
        return False

    # -- Name toggle

    def toggle_name(self):
        """
        Navigate to profile and toggle a '.' at the end of the name.
        This triggers a profile update, which refreshes your 'last updated' timestamp.

        DOM confirmed for the profile header:
            <div class="hdn">
                <span class="fullname">Mohammad Shaif Ahmed Shaikh</span>
                <span class="hide">Edit</span>
                <em class="icon edit ">editOneTheme</em>
            </div>
        The edit icon opens a modal -- its internal input field selector below is
        a best-effort fallback list since the modal DOM wasn't provided.
        """
        step(self.logger, "Toggling display name...")

        if "mnjuser/profile" not in self.driver.current_url:
            self.driver.get(self.NAUKRI_PROFILE)
            time.sleep(4)

        try:
            # -- Step 1: Click the edit icon next to the name (confirmed selector first)
            edit_selectors = [
                "div.hdn em.icon.edit",
                "em.icon.edit",
                "div.hdn em.icon",
                # legacy / fallback guesses in case Naukri changes the DOM again
                "span.edit-icon-box .editPencil",
                "span[class*='edit-icon'] .icon",
                "em.editPencil",
                "button[class*='edit-btn']",
            ]

            edit_icon = None
            for selector in edit_selectors:
                try:
                    edit_icon = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if edit_icon is None:
                warn(self.logger, "Edit icon not found, trying direct name click...")
                name_selectors = [
                    "span.fullname",
                    "div.hdn span.fullname",
                ]
                for selector in name_selectors:
                    try:
                        edit_icon = self.driver.find_element(By.CSS_SELECTOR, selector)
                        break
                    except NoSuchElementException:
                        continue

            if edit_icon is None:
                error(self.logger, "Could not find any editable name element.")
                self.take_screenshot("name_edit_not_found")
                raise NoSuchElementException("Name edit element not found")

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", edit_icon
            )
            time.sleep(0.3)

            try:
                edit_icon.click()
            except Exception:
                self.driver.execute_script("arguments[0].click();", edit_icon)

            info(self.logger, "Opened name edit dialog.")

        except Exception as e:
            error(self.logger, f"Failed to open name editor: {e}")
            self.take_screenshot("name_edit_click_fail")
            raise

        try:
            # -- Step 2: Find the name input field inside the modal
            # NOTE: the modal's HTML wasn't available when this was written.
            # If this still fails, inspect the modal after step 1 opens it and
            # add its exact selector to the top of this list.
            # (No extra flat sleep needed here -- WebDriverWait below already
            # covers the time it takes the modal/input to appear.)
            name_selectors = [
                "input[name='fullName']",
                "input[name='fname']",
                "input[placeholder*='name' i]",
                "input#name",
                "input[name='name']",
                "input[class*='name']",
                "div.modal input[type='text']",
                "form input[type='text']:first-of-type",
            ]

            name_input = None
            for selector in name_selectors:
                try:
                    name_input = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    val = name_input.get_attribute("value")
                    if val and len(val.strip()) > 0:
                        break
                    name_input = None
                except TimeoutException:
                    continue

            if name_input is None:
                error(self.logger, "Could not find the name input field.")
                self.take_screenshot("name_input_not_found")
                raise NoSuchElementException("Name input not found")

            current_name = name_input.get_attribute("value").strip()
            self.logger.debug(f"Current name value: '{current_name}'")

            if current_name.endswith("."):
                new_name = current_name[:-1]
                self.toggle_state = False
            else:
                new_name = current_name + "."
                self.toggle_state = True

            info(self.logger, f"Name change: '{current_name}' -> '{new_name}'")

            name_input.click()
            name_input.send_keys(Keys.CONTROL + "a")
            name_input.send_keys(Keys.DELETE)
            time.sleep(0.15)
            name_input.send_keys(new_name)
            time.sleep(0.2)

            # -- Step 3: Click Save button
            # Confirmed DOM: <button type="button" id="saveBasicDetailsBtn" class="btn-dark-ot">Save</button>
            # NOTE: type is "button", not "submit" -- that mismatch was the bug.
            save_selectors = [
                "#saveBasicDetailsBtn",
                "button#saveBasicDetailsBtn",
                "button.btn-dark-ot",
                "button[class*='save']",
                "button[type='submit']",
                "button:not([class*='cancel'])[class*='btn-primary']",
            ]

            save_btn = None
            for selector in save_selectors:
                try:
                    save_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if save_btn is None:
                error(self.logger, "Save button not found.")
                self.take_screenshot("save_btn_not_found")
                raise NoSuchElementException("Save button not found")

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", save_btn
            )
            time.sleep(0.2)
            save_btn.click()

            # Instead of a flat 3s sleep, wait for the save modal/button to
            # actually disappear (i.e. Naukri finished processing the save).
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, "#saveBasicDetailsBtn"))
                )
            except TimeoutException:
                # Modal may not always fully disappear from the DOM depending
                # on layout -- fall back to a short grace period.
                time.sleep(1)

            write_toggle_state(self.toggle_state)

            info(self.logger, f"Name updated successfully to: '{new_name}'")

        except NoSuchElementException:
            raise
        except TimeoutException:
            error(self.logger, "Timed out finding name input or save button.")
            self.take_screenshot("name_toggle_timeout")
            raise
        except Exception as e:
            error(self.logger, f"Name toggle failed: {e}")
            self.take_screenshot("name_toggle_error")
            raise

    # -- Resume upload

    def update_resume(self):
        """
        Upload a dated copy of the resume to Naukri.

        DOM confirmed:
            <input type="file" id="attachCV" class="fileUpload ...">
            <input type="button" value="Update resume" class="dummyUpload typ-14Bold">
            <div class="updateOn typ-14Regular">Uploaded on Jul 31, 2026</div>
            <div title="Shaif_Ahmed_Resume_31072026.pdf" class="truncate exten">...</div>
        """
        step(self.logger, "Updating resume...")

        try:
            dated_resume_path = create_dated_resume(self.config["resume_path"], self.logger)
            info(self.logger, f"Resume to upload: {os.path.basename(dated_resume_path)}")
        except FileNotFoundError as e:
            error(self.logger, str(e))
            return

        if "mnjuser/profile" not in self.driver.current_url:
            self.driver.get(self.NAUKRI_PROFILE)
            time.sleep(4)

        try:
            # -- Some Naukri layouts require clicking the visible "Update resume"
            # dummy button before the real (often visually hidden) file input
            # will accept send_keys. This is best-effort and safe to skip if
            # the button isn't present/clickable.
            try:
                dummy_btn = WebDriverWait(self.driver, 4).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input.dummyUpload"))
                )
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", dummy_btn
                )
                dummy_btn.click()
            except TimeoutException:
                self.logger.debug("dummyUpload button not found/clickable, continuing anyway.")

            # -- Find the resume upload input element (confirmed selector first)
            upload_selectors = [
                "input#attachCV",
                "input[type='file'][id='attachCV']",
                "input[type='file'][name='file']",
                "input[type='file'][id*='resume']",
                "input[type='file'][accept*='.pdf']",
                "input[type='file']",
            ]

            upload_input = None
            for selector in upload_selectors:
                try:
                    upload_input = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue

            if upload_input is None:
                error(self.logger, "Could not find resume upload input element.")
                self.take_screenshot("resume_upload_input_not_found")
                raise NoSuchElementException("Resume upload input not found")

            abs_path = os.path.abspath(dated_resume_path)
            upload_input.send_keys(abs_path)
            info(self.logger, f"Resume file sent to upload: {os.path.basename(abs_path)}")

            # -- Confirm success via the real "Uploaded on <date>" text, and
            # cross-check the new filename shows up in the file-name tile.
            # (No flat 6s sleep here -- this WebDriverWait already covers
            # however long the upload/processing actually takes.)
            dated_filename = os.path.basename(dated_resume_path)
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(@class,'updateOn') and contains(., 'Uploaded on')]")
                    )
                )
                try:
                    name_tile = self.driver.find_element(
                        By.CSS_SELECTOR, "div.resume-name-inline [title]"
                    )
                    shown_title = (name_tile.get_attribute("title") or "").strip()
                    if dated_filename.lower() in shown_title.lower():
                        info(self.logger, f"Resume uploaded and confirmed: {shown_title}")
                    else:
                        warn(self.logger, f"Upload confirmed but filename shows as '{shown_title}' "
                                           f"(expected '{dated_filename}').")
                except NoSuchElementException:
                    info(self.logger, "Resume uploaded successfully (updateOn text found).")
            except TimeoutException:
                warn(self.logger, "No 'Uploaded on' confirmation found, but file was sent.")
                self.take_screenshot("resume_upload_no_confirmation")

        except NoSuchElementException:
            raise
        except Exception as e:
            error(self.logger, f"Resume upload failed: {e}")
            self.take_screenshot("resume_upload_error")
            raise

    # -- Full update cycle

    def run_update_cycle(self) -> bool:
        cycle_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{Fore.MAGENTA}{'=' * 60}")
        print(f"{Fore.MAGENTA}  UPDATE CYCLE -- {cycle_time}")
        print(f"{Fore.MAGENTA}{'=' * 60}{Style.RESET_ALL}\n")

        retries = self.config.get("max_retries", 3)
        delay = self.config.get("retry_delay_seconds", 5)

        for attempt in range(1, retries + 1):
            try:
                if not self.driver:
                    self.start_browser()

                if not self.check_login():
                    error(self.logger, "Login failed or timed out.")
                    self.close_browser()
                    return False

                self.toggle_name()
                self.update_resume()
                self.close_browser()

                print(f"\n{Fore.GREEN}{Style.BRIGHT}  [SUCCESS] Update cycle completed successfully!")
                next_mins = self.config['update_interval_minutes']
                print(f"{Fore.CYAN}  [NEXT] Update in {next_mins} minutes ({next_mins/60:.1f} hours).{Style.RESET_ALL}\n")
                return True

            except Exception as e:
                error(self.logger, f"Attempt {attempt}/{retries} failed: {e}")
                self.logger.debug(traceback.format_exc())
                self.close_browser()

                if attempt < retries:
                    warn(self.logger, f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    error(self.logger, f"All {retries} attempts failed.")
                    return False

        return False


# ----------------------------------------------------------------
# CLI argument parsing
# ----------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Naukri Profile Auto-Updater -- keeps your profile active.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python naukri_updater.py --once       Run once and exit (for Windows Task Scheduler)
  python naukri_updater.py --loop       Run continuously with internal scheduler
  python naukri_updater.py              Same as --loop (default)
        """
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single update cycle and exit. Use this with Windows Task Scheduler."
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously with internal scheduler (default behavior)."
    )
    return parser.parse_args()


# ----------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------
def main():
    banner()
    args = parse_args()

    config = load_config()
    logger = setup_logging(config["log_file"])

    browser_name = config.get("browser", "brave").capitalize()
    info(logger, f"Configuration loaded from: {CONFIG_PATH}")
    info(logger, f"Browser: {browser_name}")
    info(logger, f"Update interval: {config['update_interval_minutes']} minutes")
    info(logger, f"Resume: {config['resume_path']}")
    info(logger, f"Profile: {config['browser_profile']}")
    info(logger, f"Headless: {config.get('headless', False)}")

    if not os.path.exists(config["resume_path"]):
        error(logger, f"Resume file not found: {config['resume_path']}")
        error(logger, "Please update 'resume_path' in config.json with the correct path.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    updater = NaukriUpdater(config, logger)

    if args.once:
        step(logger, "MODE: Single run (--once)")
        success = updater.run_update_cycle()
        sys.exit(0 if success else 1)

    step(logger, "MODE: Continuous scheduler (--loop)")
    step(logger, "Running first update cycle NOW...")
    updater.run_update_cycle()

    interval = config["update_interval_minutes"]
    schedule.every(interval).minutes.do(updater.run_update_cycle)

    info(logger, f"Scheduler active -- updates every {interval} minutes.")
    info(logger, "Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Shutting down gracefully...{Style.RESET_ALL}")
        updater.close_browser()
        info(logger, "Naukri Auto-Updater stopped by user.")
        print(f"{Fore.GREEN}Goodbye!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()