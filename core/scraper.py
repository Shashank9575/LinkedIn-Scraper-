"""
LinkedIn Lead Generator — Main Scraper Orchestrator
=====================================================
Coordinates the entire pipeline:
1. Login to LinkedIn
2. Search for companies by industry
3. Scrape company profiles
4. Find decision makers (Founders, CMOs, Marketing Managers)
5. Send connection requests with personalized notes
6. Follow up with DMs on accepted connections

Mirrors the architecture of the Instagram scraper for consistency.
"""

import json
import random
import ssl
import time
import urllib3
from pathlib import Path
from typing import Dict, List, Optional, Set, Any

# ── SSL patch for corporate proxy / firewall ──────────────────────────────────
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_ssl = ssl.create_default_context
def _no_verify(*a, **kw):
    ctx = _orig_ssl(*a, **kw)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
ssl.create_default_context = _no_verify
ssl._create_default_https_context = ssl._create_unverified_context
# ──────────────────────────────────────────────────────────────────────────────

from core.linkedin_search import LinkedInSearch
from core.company_fetcher import CompanyFetcher
from core.people_finder import PeopleFinder
from core.messenger import LinkedInMessenger, personalize_message
from utils.exporter import CSVExporter
from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()


class LinkedInScraper:
    """
    Main orchestrator for the LinkedIn Lead Generation pipeline.
    """

    def __init__(self, industries: Optional[List[str]] = None):
        self.industries = industries or g_settings.INDUSTRIES
        self._seen_companies: Set[str] = set()
        self._load_checkpoint()
        self._driver = None
        self._search: Optional[LinkedInSearch] = None
        self._fetcher: Optional[CompanyFetcher] = None
        self._finder: Optional[PeopleFinder] = None
        self._messenger: Optional[LinkedInMessenger] = None
        self._request_count = 0
        self._current_account_idx = 0
        self._profiles_this_session = 0
        self._exporter = CSVExporter(filepath=g_settings.OUTPUT_CSV)
        self._total_saved = 0
        self._total_connections_sent = 0
        self._total_dms_sent = 0
        self._connection_failures: List[str] = []
        self._accounts_used_session = 1
        self._all_accounts_exhausted = False

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> List[Dict[str, Any]]:
        """
        Full pipeline: Search → Scrape → Find People → Connect.
        """
        all_leads: List[Dict] = []
        logger.info(f"Starting — {len(self.industries)} industries")
        logger.info(f"Mode: {g_settings.OPERATION_MODE.upper()}")
        logger.info(f"Connect: {'ON' if g_settings.SEND_CONNECTION_REQUESTS else 'OFF'}")
        logger.info(f"DM: {'ON' if g_settings.SEND_DMS else 'OFF'}")
        logger.info(f"Output: {g_settings.OUTPUT_CSV}")

        # Step 1: Login to LinkedIn
        self._linkedin_login()

        interrupted = False
        try:
            for idx, industry in enumerate(self.industries, 1):
                if getattr(self, '_all_accounts_exhausted', False):
                    break
                logger.info(f"\n{'='*60}")
                logger.info(f"[{idx}/{len(self.industries)}] Industry: {industry}")
                logger.info(f"{'='*60}")

                try:
                    leads = self._process_industry(industry)
                    all_leads.extend(leads)
                    self._save_checkpoint()
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error processing industry '{industry}': {e}")

                if idx < len(self.industries):
                    delay = random.uniform(
                        g_settings.INDUSTRY_DELAY_MIN,
                        g_settings.INDUSTRY_DELAY_MAX
                    )
                    logger.info(f"Waiting {delay:.0f}s before next industry...")
                    time.sleep(delay)

        except KeyboardInterrupt:
            logger.warning("\n⚠ Interrupted by user.")
            interrupted = True

        # Cleanup
        self._save_checkpoint()
        self._cleanup()

        logger.info(f"\nTotal leads saved: {self._total_saved}")
        logger.info(f"Connections sent: {self._total_connections_sent}")
        logger.info(f"DMs sent: {self._total_dms_sent}")

        if interrupted:
            raise KeyboardInterrupt

        return all_leads

    def run_search_only(self) -> List[Dict[str, Any]]:
        """Search and scrape only — no outreach."""
        original_connect = g_settings.SEND_CONNECTION_REQUESTS
        original_dm = g_settings.SEND_DMS
        g_settings.SEND_CONNECTION_REQUESTS = False
        g_settings.SEND_DMS = False

        try:
            return self.run()
        finally:
            g_settings.SEND_CONNECTION_REQUESTS = original_connect
            g_settings.SEND_DMS = original_dm

    def run_followup(self) -> int:
        """Check accepted connections and send follow-up DMs."""
        logger.info("Starting follow-up mode — checking accepted connections...")

        self._linkedin_login()

        messenger = self._get_messenger()
        accepted = messenger.get_pending_connections()
        dm_count = 0

        if not accepted:
            logger.info("No accepted connections to follow up on")
            self._cleanup()
            return 0

        # Cross-reference with our CSV to find leads that need DMs
        existing_records = self._exporter.get_all_records()
        pending_dms = []

        for record in existing_records:
            if record.get("connection_status") == "sent" and record.get("dm_sent") != "True":
                # Normalize the record URL for comparison
                record_url = record.get("decision_maker_linkedin", "")
                record_url = record_url.rstrip('/').split('?')[0].lower().replace('https://www.linkedin.com', '').replace('https://linkedin.com', '')
                for acc in accepted:
                    acc_url = acc.get("linkedin_url", "")
                    acc_url = acc_url.rstrip('/').split('?')[0].lower().replace('https://www.linkedin.com', '').replace('https://linkedin.com', '')
                    if acc_url and record_url and acc_url == record_url:
                        pending_dms.append(record)
                        break

        logger.info(f"Found {len(pending_dms)} leads ready for follow-up DMs")

        for lead in pending_dms:
            if dm_count >= g_settings.MAX_DMS_PER_DAY:
                logger.warning(f"Daily DM limit reached ({g_settings.MAX_DMS_PER_DAY})")
                break

            # Personalize the DM
            industry = lead.get("industry", "default")
            template = g_settings.DM_TEMPLATES.get(
                industry, g_settings.DM_TEMPLATES.get("default", "")
            )
            message = personalize_message(
                template,
                name=lead.get("decision_maker_name", ""),
                company=lead.get("company_name", ""),
                industry=industry,
                title=lead.get("decision_maker_title", ""),
            )

            profile_url = lead.get("decision_maker_linkedin", "")
            if messenger.send_dm(profile_url, message):
                dm_count += 1
                self._total_dms_sent += 1

                # Update CSV record
                self._exporter.update_record(
                    lead.get("company_linkedin_url", ""),
                    profile_url,
                    {
                        "connection_status": "connected",
                        "dm_sent": "True",
                        "dm_message": (message[:200] + "...") if len(message) > 200 else message,
                    }
                )

        self._cleanup()
        logger.info(f"Follow-up complete — sent {dm_count} DMs")
        return dm_count

    def total_requests(self) -> int:
        total = self._request_count
        if self._fetcher:
            total += self._fetcher.total_requests()
        if self._finder:
            total += self._finder.total_requests()
        return total

    # ── Industry Processing ───────────────────────────────────────────────────

    def _process_industry(self, industry: str) -> List[Dict]:
        """Process a single industry: search companies → scrape → find people → connect."""
        keywords = g_settings.INDUSTRY_KEYWORDS.get(industry, [industry])
        search = self._get_search()
        all_leads = []

        for keyword in keywords:
            if getattr(self, '_all_accounts_exhausted', False):
                break
            if len(all_leads) >= g_settings.MAX_COMPANIES_PER_INDUSTRY:
                break

            remaining = g_settings.MAX_COMPANIES_PER_INDUSTRY - len(all_leads)
            companies = search.search_companies(keyword, max_results=remaining)

            for company_info in companies:
                if len(all_leads) >= g_settings.MAX_COMPANIES_PER_INDUSTRY:
                    break

                company_url = company_info.get("linkedin_url", "")
                if company_url in self._seen_companies:
                    logger.debug(f"  Skipping already-seen company: {company_info.get('name')}")
                    continue

                self._seen_companies.add(company_url)

                try:
                    lead = self._process_company(company_info, industry, keyword)
                    if lead:
                        all_leads.append(lead)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.debug(f"  Error processing {company_info.get('name')}: {e}")

                # Rate limiting between profile views
                self._rate_limit()

                # Account rotation check
                self._profiles_this_session += 1
                if self._profiles_this_session >= g_settings.MAX_PROFILES_PER_DAY:
                    logger.warning(f"  Daily profile view limit reached for current account.")
                    
                    if self._accounts_used_session < len(g_settings.ACCOUNTS):
                        self._switch_account()
                        self._accounts_used_session += 1
                    else:
                        logger.warning("  All accounts exhausted for this session.")
                        self._all_accounts_exhausted = True
                        break

            if getattr(self, '_all_accounts_exhausted', False):
                break

        logger.info(f"  Industry '{industry}': {len(all_leads)} leads found")
        return all_leads

    def _process_company(
        self, company_info: Dict, industry: str, source_keyword: str
    ) -> Optional[Dict]:
        """Process a single company: fetch details → find people → connect."""
        fetcher = self._get_fetcher()
        company_url = company_info.get("linkedin_url", "")

        # Step 1: Fetch company details
        company_data = fetcher.fetch(company_url, source_keyword=source_keyword)
        if not company_data:
            return None

        company_data["industry"] = industry

        # Step 2: Find decision makers
        search = self._get_search()
        finder = self._get_finder()

        # Try to use the exact numeric ID extracted from the company page
        company_id = company_data.get("company_numeric_id")
        if not company_id:
            # Fallback to URL slug, though LinkedIn Search prefers numeric IDs
            company_id = company_url.rstrip("/").split("/")[-1]

        people = search.search_people_at_company(
            company_name=company_data["company_name"],
            company_linkedin_id=company_id,
            max_results=g_settings.MAX_PEOPLE_PER_COMPANY,
        )

        # If search didn't find anyone, try the company people page
        if not people:
            people = finder.find_decision_makers_on_company_page(
                company_url,
                max_people=g_settings.MAX_PEOPLE_PER_COMPANY,
            )

        if not people:
            logger.info(f"  No decision makers found at {company_data['company_name']}")
            # Still save the company data without person info
            lead = {**company_data, "decision_maker_name": "", "decision_maker_title": "",
                    "decision_maker_linkedin": "", "connection_status": "no_person_found"}
            self._save_lead_now(lead)
            return lead

        # Step 3: Process each decision maker
        best_lead = None
        for person in people:
            self._rate_limit()

            # Visit person's profile for more details
            person_data = finder.fetch_person(person["linkedin_url"])
            if not person_data:
                continue

            lead = {
                **company_data,
                "decision_maker_name": person_data.get("name", person.get("name", "")),
                "decision_maker_title": person_data.get("title", person.get("title", "")),
                "decision_maker_linkedin": person_data.get("linkedin_url", person["linkedin_url"]),
                "connection_status": "not_sent",
            }

            # Step 4: Send connection request (if enabled)
            if g_settings.SEND_CONNECTION_REQUESTS:
                if person_data.get("can_connect"):
                    note = personalize_message(
                        g_settings.CONNECTION_NOTE,
                        name=person_data.get("name", "").split()[0] if person_data.get("name") else "",
                        company=company_data.get("company_name", ""),
                        industry=industry,
                        title=person_data.get("title", ""),
                    )
                    # LinkedIn enforces 300-char limit on connection notes
                    if len(note) > 300:
                        note = note[:297] + "..."

                    messenger = self._get_messenger()
                    # Pass skip_navigation=True since we already visited the profile
                    if messenger.send_connection_request(person["linkedin_url"], note, skip_navigation=True):
                        lead["connection_status"] = "sent"
                        self._total_connections_sent += 1
                    else:
                        lead["connection_status"] = "failed"
                        self._connection_failures.append(person["linkedin_url"])

                elif person_data.get("can_message"):
                    # Already connected — send DM directly
                    lead["connection_status"] = "connected"

                    if g_settings.SEND_DMS:
                        template = g_settings.DM_TEMPLATES.get(
                            industry, g_settings.DM_TEMPLATES.get("default", "")
                        )
                        message = personalize_message(
                            template,
                            name=person_data.get("name", "").split()[0] if person_data.get("name") else "",
                            company=company_data.get("company_name", ""),
                            industry=industry,
                            title=person_data.get("title", ""),
                        )

                        messenger = self._get_messenger()
                        if messenger.send_dm(person["linkedin_url"], message):
                            lead["dm_sent"] = True
                            lead["dm_message"] = message[:200] + "..."
                            self._total_dms_sent += 1

            # Save lead to CSV
            self._save_lead_now(lead)
            best_lead = lead
            break  # Usually we only need the top decision maker

        return best_lead

    # ── LinkedIn Login ────────────────────────────────────────────────────────

    def _linkedin_login(self, account=None):
        """Login to LinkedIn — cookie restore → automated → manual fallback."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        driver = self._get_driver()

        if account is None:
            if not g_settings.ACCOUNTS:
                logger.warning("No LinkedIn accounts configured in .env! Forcing manual login.")
                username = "Manual_User"
                password = ""
            else:
                account = g_settings.ACCOUNTS[self._current_account_idx % len(g_settings.ACCOUNTS)]
                username = account.get("username", "")
                password = account.get("password", "")
        else:
            username = account.get("username", "")
            password = account.get("password", "")

        # Step 1: Try loading saved session (cookies)
        cookies_path = Path(f"li_cookies_{username.replace('@', '_').replace('.', '_')}.json")

        if cookies_path.exists():
            logger.info(f"Loading saved LinkedIn session for {username}...")
            driver.get("https://www.linkedin.com/")
            time.sleep(3)

            try:
                with open(cookies_path, "r", encoding="utf-8") as f:
                    cookies = json.load(f)

                safe_cookies = self._sanitize_cookies(cookies)
                for cookie in safe_cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as e:
                        logger.debug(f"Skipped cookie {cookie.get('name')}: {e}")

                driver.refresh()
                time.sleep(4)
                self._dismiss_popups(driver)

                if self._is_logged_in(driver):
                    logger.info(f"✅ Logged in via saved cookies as {username}")
                    return
                else:
                    logger.warning("Saved session expired — will try fresh login")
            except Exception as e:
                logger.warning(f"Could not load cookies: {e}")

        # Step 2: Automated login
        if username and password:
            logger.info(f"Attempting automated login as {username}...")
            if self._try_automated_login(driver, username, password):
                return
            logger.warning("Automated login failed — falling back to manual login")

        # Step 3: Manual login fallback
        logger.info(f"Opening LinkedIn for manual login ({username})...")
        driver.get("https://www.linkedin.com/login")
        time.sleep(3)

        if self._is_logged_in(driver):
            logger.info(f"✅ Already logged in as {username}")
            self._save_cookies(driver, username)
            return

        print("\n" + "=" * 60)
        print(f"  🔐 MANUAL LOGIN REQUIRED: {username}")
        print("=" * 60)
        print("  Please log in to LinkedIn in the browser window.")
        print("  When fully logged in, come back here and press ENTER.")
        print("=" * 60)
        input("\n  Press ENTER when login is complete... ")
        print()

        time.sleep(3)
        self._dismiss_popups(driver)

        if self._is_logged_in(driver):
            logger.info(f"✅ Manual login successful for {username}")
            self._save_cookies(driver, username)
        else:
            logger.warning("⚠ Login could not be verified — continuing anyway")
            self._save_cookies(driver, username)

    def _try_automated_login(self, driver, username: str, password: str) -> bool:
        """Attempt automated login with credentials."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException

        try:
            driver.get("https://www.linkedin.com/login")
            wait = WebDriverWait(driver, 20)
            time.sleep(3)

            # Username field
            try:
                user_field = wait.until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
            except TimeoutException:
                user_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='session_key']"))
                )

            user_field.clear()
            for char in username:
                user_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))

            # Password field
            try:
                pass_field = driver.find_element(By.ID, "password")
            except Exception:
                pass_field = driver.find_element(By.CSS_SELECTOR, "input[name='session_password']")

            pass_field.clear()
            for char in password:
                pass_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.12))

            time.sleep(random.uniform(1.0, 2.0))

            # Click sign in
            try:
                submit_btn = driver.find_element(By.XPATH, "//button[@type='submit']")
                submit_btn.click()
            except Exception:
                from selenium.webdriver.common.keys import Keys
                pass_field.send_keys(Keys.RETURN)

            logger.info("Login submitted — waiting for redirect...")
            time.sleep(8)

            # Check for security challenge
            if "checkpoint" in driver.current_url or "challenge" in driver.current_url:
                logger.warning("⚠ LinkedIn security challenge detected!")
                logger.warning("👉 Complete it manually in the browser (120 sec timeout)")
                time.sleep(120)

            self._dismiss_popups(driver)

            if self._is_logged_in(driver):
                logger.info(f"✓ Logged in successfully as {username}")
                self._save_cookies(driver, username)
                return True

            return False

        except Exception as e:
            logger.warning(f"Automated login error: {e}")
            return False

    def _is_logged_in(self, driver) -> bool:
        """Check if currently logged in to LinkedIn."""
        try:
            cookies = driver.get_cookies()
            # LinkedIn uses 'li_at' cookie for authentication
            if any(c['name'] == 'li_at' for c in cookies):
                return True

            # Fallback: check URL
            current = driver.current_url
            if "feed" in current or "mynetwork" in current:
                return True

            # Fallback: check for nav elements
            try:
                driver.find_element(By.CSS_SELECTOR, "nav[aria-label='Primary']")
                return True
            except Exception:
                pass

        except Exception:
            pass
        return False

    # ── Driver & Component Setup ──────────────────────────────────────────────

    def _get_driver(self):
        """Get or create the undetected Chrome driver."""
        if self._driver is None:
            import undetected_chromedriver as uc
            import re

            def build_options():
                opt = uc.ChromeOptions()
                if g_settings.HEADLESS:
                    opt.add_argument("--headless=new")
                opt.add_argument("--no-sandbox")
                opt.add_argument("--disable-dev-shm-usage")
                opt.add_argument("--disable-blink-features=AutomationControlled")
                opt.add_argument("--start-maximized")
                opt.add_argument("--lang=en-US")

                # Proxy support
                if g_settings.USE_PROXY and g_settings.PROXY_HOST:
                    if g_settings.PROXY_USER:
                        from utils.proxy_util import create_proxy_extension
                        ext_path = create_proxy_extension(
                            g_settings.PROXY_HOST,
                            g_settings.PROXY_PORT,
                            g_settings.PROXY_USER,
                            g_settings.PROXY_PASS,
                        )
                        if ext_path:
                            opt.add_argument(f"--load-extension={ext_path}")
                    else:
                        opt.add_argument(
                            f"--proxy-server=http://{g_settings.PROXY_HOST}:{g_settings.PROXY_PORT}"
                        )
                return opt

            options = build_options()

            try:
                self._driver = uc.Chrome(options=options)
                logger.info("Chrome browser launched (undetected-chromedriver)")
            except Exception as e:
                error_msg = str(e)
                if "This version of ChromeDriver only supports Chrome version" in error_msg or "Current browser version is" in error_msg:
                    match = re.search(r'Current browser version is (\d+)', error_msg)
                    if match:
                        version_main = int(match.group(1))
                        logger.warning(f"ChromeDriver version mismatch. Retrying with version_main={version_main}...")
                        # undetected-chromedriver doesn't allow reusing options, so we build a fresh one
                        fresh_options = build_options()
                        self._driver = uc.Chrome(options=fresh_options, version_main=version_main)
                        logger.info(f"Chrome browser launched (undetected-chromedriver) with version fallback: {version_main}")
                    else:
                        raise e
                else:
                    raise e

        return self._driver

    def _get_search(self) -> LinkedInSearch:
        if self._search is None:
            self._search = LinkedInSearch(self._get_driver())
        return self._search

    def _get_fetcher(self) -> CompanyFetcher:
        if self._fetcher is None:
            self._fetcher = CompanyFetcher(self._get_driver())
        return self._fetcher

    def _get_finder(self) -> PeopleFinder:
        if self._finder is None:
            self._finder = PeopleFinder(self._get_driver())
        return self._finder

    def _get_messenger(self) -> LinkedInMessenger:
        if self._messenger is None:
            self._messenger = LinkedInMessenger(self._get_driver())
        return self._messenger

    # ── Save & Export ─────────────────────────────────────────────────────────

    def _save_lead_now(self, lead: Dict):
        """Write this single lead to CSV immediately."""
        try:
            stats = self._exporter.export([lead])
            if stats["new"] > 0:
                self._total_saved += 1
                logger.info(
                    f"  💾 Saved: {lead.get('company_name', '?')} | "
                    f"{lead.get('decision_maker_name', 'N/A')} | "
                    f"{lead.get('industry', '?')} (total: {self._total_saved})"
                )
        except Exception as e:
            logger.warning(f"  Save error: {e}")

    # ── Checkpoint ────────────────────────────────────────────────────────────

    def _save_checkpoint(self):
        """Save progress to resume later."""
        try:
            Path(g_settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
            data = {
                "seen_companies": list(self._seen_companies),
                "total_saved": self._total_saved,
                "connections_sent": self._total_connections_sent,
                "dms_sent": self._total_dms_sent,
            }
            with open(g_settings.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug("Checkpoint saved")
        except Exception as e:
            logger.warning(f"Checkpoint save failed: {e}")

    def _load_checkpoint(self):
        """Load previous progress."""
        try:
            cp = Path(g_settings.CHECKPOINT_FILE)
            if cp.exists():
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._seen_companies = set(data.get("seen_companies", []))
                logger.info(
                    f"Checkpoint loaded — {len(self._seen_companies)} companies already processed"
                )
        except Exception as e:
            logger.debug(f"No checkpoint to load: {e}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _rate_limit(self):
        """Human-like delay between profile views."""
        delay = random.uniform(
            g_settings.PROFILE_VIEW_DELAY_MIN,
            g_settings.PROFILE_VIEW_DELAY_MAX
        )
        logger.debug(f"  Waiting {delay:.0f}s...")
        time.sleep(delay)

    def _sanitize_cookies(self, cookies):
        """Strip keys that cause Selenium add_cookie() to fail."""
        safe_cookies = []
        for cookie in cookies:
            clean = {
                "name": cookie.get("name"),
                "value": cookie.get("value"),
                "domain": cookie.get("domain"),
                "path": cookie.get("path", "/"),
            }
            if cookie.get("secure"):
                clean["secure"] = cookie["secure"]
            if cookie.get("httpOnly"):
                clean["httpOnly"] = cookie["httpOnly"]
            safe_cookies.append(clean)
        return safe_cookies

    def _save_cookies(self, driver, username: str):
        """Save current session cookies."""
        try:
            safe_name = username.replace("@", "_").replace(".", "_")
            with open(f"li_cookies_{safe_name}.json", "w", encoding="utf-8") as f:
                json.dump(driver.get_cookies(), f)
            logger.info(f"💾 Session saved for {username}")
        except Exception as e:
            logger.warning(f"Could not save cookies: {e}")

    def _dismiss_popups(self, driver):
        """Dismiss LinkedIn popups."""
        popup_xpaths = [
            '//button[contains(@aria-label, "Dismiss")]',
            '//button[contains(text(), "Got it")]',
            '//button[contains(text(), "Not now")]',
            '//button[contains(text(), "Skip")]',
            '//button[contains(@aria-label, "Close")]',
            '//button[contains(@class, "msg-overlay-bubble-header__control--close-btn")]',
        ]
        for xpath in popup_xpaths:
            try:
                from selenium.webdriver.common.by import By
                btn = driver.find_element(By.XPATH, xpath)
                btn.click()
                time.sleep(0.5)
            except Exception:
                continue

    def _switch_account(self):
        """Rotate to next LinkedIn account."""
        if len(g_settings.ACCOUNTS) <= 1:
            return

        self._current_account_idx += 1
        next_account = g_settings.ACCOUNTS[self._current_account_idx % len(g_settings.ACCOUNTS)]
        logger.info(f"\n🔄 Switching to account: {next_account['username']}...")

        driver = self._get_driver()
        driver.delete_all_cookies()
        time.sleep(2)

        # Invalidate stale component references so they rebind after login
        self._search = None
        self._fetcher = None
        self._finder = None
        self._messenger = None

        self._linkedin_login(account=next_account)
        self._profiles_this_session = 0

    def _cleanup(self):
        """Close browser and save state."""
        if self._driver:
            try:
                self._driver.quit()
                logger.info("Chrome browser closed")
            except Exception:
                pass
            self._driver = None

        self._search = None
        self._fetcher = None
        self._finder = None
        self._messenger = None
