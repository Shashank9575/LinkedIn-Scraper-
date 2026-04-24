"""
People Finder — Decision Maker Discovery
==========================================
Finds founders, CEOs, CMOs, and marketing managers at target companies.
Visits their LinkedIn profiles to extract detailed info.
"""

import re
import time
import random
from typing import Dict, Optional, List

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)

from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()


class PeopleFinder:
    """
    Finds and profiles decision makers (founders, marketing heads)
    at target companies on LinkedIn.
    """

    def __init__(self, driver):
        self.driver = driver
        self._request_count = 0

    def total_requests(self) -> int:
        return self._request_count

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_person(self, profile_url: str) -> Optional[Dict]:
        """
        Visit a LinkedIn person's profile and extract detailed info.

        Returns dict with: name, title, linkedin_url, company, location,
                          connection_degree, can_message, about
        """
        logger.info(f"  👤 Visiting profile: {profile_url}")

        try:
            self.driver.get(profile_url)
            self._request_count += 1
            time.sleep(random.uniform(3.0, 5.0))
            self._close_popups()
        except Exception as e:
            logger.error(f"  Could not load profile: {e}")
            return None

        data = {
            "linkedin_url": profile_url.rstrip("/").split("?")[0],
        }

        # Extract name
        data["name"] = self._extract_name()
        if not data["name"]:
            logger.warning(f"  Could not extract name from {profile_url}")
            return None

        # Extract headline/title
        data["title"] = self._extract_headline()

        # Extract current company
        data["company"] = self._extract_current_company()

        # Extract location
        data["location"] = self._extract_location()

        # Check connection degree
        data["connection_degree"] = self._extract_connection_degree()

        # Check if we can message them
        data["can_message"] = self._check_can_message()

        # Check if connect button is available
        data["can_connect"] = self._check_can_connect()

        logger.info(
            f"  ✓ {data['name']} | {data['title']} | "
            f"{data['connection_degree']} | "
            f"{'Can DM' if data['can_message'] else 'Connect first'}"
        )

        return data

    def find_decision_makers_on_company_page(
        self, company_url: str, max_people: int = 3
    ) -> List[Dict]:
        """
        Visit company's people tab and find decision makers directly.
        Alternative to search-based discovery.
        """
        people_url = company_url.rstrip("/") + "/people/"
        logger.info(f"  👥 Checking company people page: {people_url}")

        try:
            self.driver.get(people_url)
            self._request_count += 1
            time.sleep(random.uniform(3.0, 5.0))
            self._close_popups()
        except Exception as e:
            logger.error(f"  Could not load people page: {e}")
            return []

        people = []

        # Try to use the keyword filter on the people page
        try:
            # Look for search input on the people page
            search_input = None
            for sel in [
                "input[placeholder*='Search']",
                "input[aria-label*='Search']",
                "input[type='text']",
            ]:
                try:
                    search_input = self.driver.find_element(By.CSS_SELECTOR, sel)
                    break
                except NoSuchElementException:
                    continue

            if search_input:
                # Search for common decision maker titles
                for search_term in ["founder", "CEO", "marketing", "CMO"]:
                    try:
                        search_input.clear()
                        time.sleep(0.5)
                        search_input.send_keys(search_term)
                        time.sleep(2.0)

                        # Wait for filtered results
                        time.sleep(random.uniform(2.0, 3.0))

                        # Extract people cards
                        cards = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            "li.org-people-profile-card__profile-card-spacing"
                        )

                        for card in cards:
                            if len(people) >= max_people:
                                break

                            person = self._extract_person_from_company_card(card)
                            if person:
                                # Check for duplicates
                                if not any(
                                    p["linkedin_url"] == person["linkedin_url"]
                                    for p in people
                                ):
                                    people.append(person)

                        if len(people) >= max_people:
                            break

                    except Exception as e:
                        logger.debug(f"  Search for '{search_term}' failed: {e}")
                        continue

        except Exception as e:
            logger.debug(f"  People page search failed: {e}")

        # If search didn't work, try to extract from default listing
        if not people:
            try:
                # Scroll to load people
                for _ in range(3):
                    self.driver.execute_script(
                        "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    time.sleep(g_settings.SCROLL_PAUSE)

                cards = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "li.org-people-profile-card__profile-card-spacing"
                )

                for card in cards:
                    if len(people) >= max_people * 2:  # Get more, filter later
                        break

                    person = self._extract_person_from_company_card(card)
                    if person:
                        # Filter by target roles
                        title_lower = person.get("title", "").lower()
                        is_target = any(
                            role.lower() in title_lower
                            for role in g_settings.TARGET_ROLES
                        )
                        if is_target:
                            people.append(person)

            except Exception as e:
                logger.debug(f"  Default people extraction failed: {e}")

        logger.info(f"  Found {len(people)} decision makers on company people page")
        return people[:max_people]

    # ── Profile Field Extraction ──────────────────────────────────────────────

    def _extract_name(self) -> str:
        """Extract person's name from profile page."""
        for selector in [
            "h1.text-heading-xlarge",
            "h1.top-card-layout__title",
            "h1[class*='inline']",
            "h1",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                name = el.text.strip()
                if name and name != "LinkedIn Member":
                    return name
            except NoSuchElementException:
                continue
        return ""

    def _extract_headline(self) -> str:
        """Extract headline/job title."""
        for selector in [
            "div.text-body-medium.break-words",
            "h2.top-card-layout__headline",
            "div[class*='text-body-medium']",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return ""

    def _extract_current_company(self) -> str:
        """Extract current company from experience or headline."""
        # Try experience section first
        try:
            exp_section = self.driver.find_element(
                By.CSS_SELECTOR,
                "section[id='experience'] li:first-child"
            )
            company_el = exp_section.find_element(
                By.CSS_SELECTOR,
                "span.t-14.t-normal"
            )
            return company_el.text.strip().split(" · ")[0]
        except NoSuchElementException:
            pass

        # Fallback: extract from headline
        headline = self._extract_headline()
        if " at " in headline:
            return headline.split(" at ")[-1].strip()
        if " @ " in headline:
            return headline.split(" @ ")[-1].strip()

        return ""

    def _extract_location(self) -> str:
        """Extract location from profile."""
        for selector in [
            "span.text-body-small.inline.t-black--light.break-words",
            "div.top-card-layout__first-subline span",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                return el.text.strip()
            except NoSuchElementException:
                continue
        return ""

    def _extract_connection_degree(self) -> str:
        """Extract connection degree (1st, 2nd, 3rd+)."""
        # Method 1: Dedicated degree badge elements
        for selector in [
            "span.dist-value",
            "span[class*='distance-badge']",
            "span.pv-text-details__separator + span",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = el.text.strip().lower()
                if "1st" in text:
                    return "1st"
                elif "2nd" in text:
                    return "2nd"
                elif "3rd" in text or "3rd+" in text:
                    return "3rd+"
            except NoSuchElementException:
                continue

        # Method 2: Check only the top profile card area (not the whole page)
        try:
            header = self.driver.find_element(By.CSS_SELECTOR, "section.pv-top-card, main.scaffold-layout__main")
            header_text = header.text[:600]  # Only first 600 chars of the header
            if "1st" in header_text:
                return "1st"
            elif "2nd" in header_text:
                return "2nd"
            elif "3rd" in header_text:
                return "3rd+"
        except Exception:
            pass

        return "unknown"

    def _check_can_message(self) -> bool:
        """Check if the 'Message' button is available (1st degree connection)."""
        try:
            msg_btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Message') or contains(@aria-label, 'Message')]"
            )
            for btn in msg_btns:
                if btn.is_displayed():
                    return True
        except Exception:
            pass
        return False

    def _check_can_connect(self) -> bool:
        """Check if the 'Connect' button is available or if person is 2nd/3rd degree."""
        # Method 1: Check for visible Connect button
        try:
            connect_btns = self.driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Connect') or contains(@aria-label, 'Connect') or .//span[text()='Connect']]"
            )
            for btn in connect_btns:
                if btn.is_displayed():
                    btn_text = btn.text.strip().lower()
                    if "connect" in btn_text and "connected" not in btn_text and "pending" not in btn_text:
                        return True
        except Exception:
            pass
            
        # Method 2: Check connection degree (Connect might be under 'More')
        degree = self._extract_connection_degree()
        if degree in ["2nd", "3rd+", "unknown"]:
            return True
            
        return False

    # ── Company People Card Extraction ────────────────────────────────────────

    def _extract_person_from_company_card(self, card) -> Optional[Dict]:
        """Extract person info from a company people page card."""
        try:
            result = {}

            # Name and URL
            try:
                link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                result["linkedin_url"] = link.get_attribute("href").split("?")[0]

                name_el = link.find_element(By.CSS_SELECTOR, "div.org-people-profile-card__profile-title")
                result["name"] = name_el.text.strip()
            except NoSuchElementException:
                try:
                    link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                    result["linkedin_url"] = link.get_attribute("href").split("?")[0]
                    result["name"] = link.text.strip().split("\n")[0]
                except NoSuchElementException:
                    return None

            if not result.get("name"):
                return None

            # Title
            try:
                title_el = card.find_element(
                    By.CSS_SELECTOR,
                    "div.artdeco-entity-lockup__subtitle"
                )
                result["title"] = title_el.text.strip()
            except NoSuchElementException:
                result["title"] = ""

            result["connection_degree"] = "unknown"
            return result

        except StaleElementReferenceException:
            return None
        except Exception as e:
            logger.debug(f"  Company card extraction error: {e}")
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _close_popups(self):
        """Dismiss common LinkedIn popups."""
        popup_xpaths = [
            '//button[contains(@aria-label, "Dismiss")]',
            '//button[contains(text(), "Got it")]',
            '//button[contains(text(), "Not now")]',
            '//button[contains(text(), "Skip")]',
            '//button[contains(@aria-label, "Close")]',
        ]
        for xpath in popup_xpaths:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                btn.click()
                time.sleep(0.5)
            except NoSuchElementException:
                continue
            except Exception:
                continue
