"""
LinkedIn Search Engine
=======================
Searches LinkedIn for companies and people by industry/keywords.
Uses Selenium to navigate LinkedIn search pages.
"""

import re
import time
import random
from typing import List, Dict, Optional, Set
from urllib.parse import quote_plus

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


class LinkedInSearch:
    """
    Searches LinkedIn for companies and people.
    Operates on the same Chrome driver used for login and other actions.
    """

    def __init__(self, driver):
        self.driver = driver

    # ── Company Search ────────────────────────────────────────────────────────

    def search_companies(
        self, keyword: str, max_results: int = 20
    ) -> List[Dict[str, str]]:
        """
        Search LinkedIn for companies matching a keyword.

        Returns list of dicts: {name, linkedin_url, tagline, location}
        """
        encoded = quote_plus(keyword)
        search_url = (
            f"https://www.linkedin.com/search/results/companies/"
            f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
        )

        logger.info(f"  🔍 Searching companies: '{keyword}'")
        companies: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        page = 1
        while page <= g_settings.MAX_SEARCH_PAGES and len(companies) < max_results:
            page_url = f"{search_url}&page={page}" if page > 1 else search_url

            try:
                self.driver.get(page_url)
                time.sleep(random.uniform(3.0, 5.0))
                self._close_popups()

                # Wait for search results to load
                try:
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.search-results-container")
                        )
                    )
                except TimeoutException:
                    # Fallback: wait for any list items
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "ul.reusable-search__entity-result-list")
                            )
                        )
                    except TimeoutException:
                        logger.warning(f"  Search results did not load for page {page}")
                        break

                # Scroll to load all results on this page
                self._scroll_page()

                # Extract company cards
                cards = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "div[data-chameleon-result-urn], li.reusable-search__result-container, div.search-entity-media"
                )

                if not cards:
                    logger.info(f"  No more results on page {page}")
                    break

                for card in cards:
                    if len(companies) >= max_results:
                        break

                    company = self._extract_company_from_card(card)
                    if company and company["linkedin_url"] not in seen_urls:
                        seen_urls.add(company["linkedin_url"])
                        companies.append(company)
                        logger.debug(
                            f"    Found: {company['name']} ({company.get('location', '?')})"
                        )

                logger.info(f"  Page {page}: found {len(cards)} results, total {len(companies)}")
                page += 1

                if page <= g_settings.MAX_SEARCH_PAGES:
                    time.sleep(random.uniform(
                        g_settings.SEARCH_DELAY_MIN,
                        g_settings.SEARCH_DELAY_MAX
                    ))

            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"  Search error on page {page}: {e}")
                break

        logger.info(f"  Search '{keyword}': {len(companies)} companies found")
        return companies

    # ── People Search ─────────────────────────────────────────────────────────

    def search_people_at_company(
        self,
        company_name: str,
        company_linkedin_id: str = "",
        roles: List[str] = None,
        max_results: int = 3,
    ) -> List[Dict[str, str]]:
        """
        Search LinkedIn for people at a specific company with target roles.
        Uses a multi-pass strategy for maximum accuracy:
          Pass 1: Use currentCompany filter (most accurate, needs numeric ID)
          Pass 2: Boolean keyword search with strict company name matching
          Pass 3: Relaxed keyword search (company name + role in keywords)

        Returns list of dicts: {name, title, linkedin_url, connection_degree}
        """
        if roles is None:
            roles = g_settings.TARGET_ROLES

        people: List[Dict[str, str]] = []
        seen_urls: Set[str] = set()

        import re
        # Clean company name to improve search accuracy (remove legal suffixes)
        clean_company = re.sub(r'(?i)\b(inc|llc|ltd|corp|co|limited|corporation|group|pvt|private)\b\.?', '', company_name).strip()
        # Remove extra whitespace from cleanup
        clean_company = re.sub(r'\s+', ' ', clean_company).strip()

        # Priority roles for search query (LinkedIn limits query length)
        priority_roles = roles[:4]
        role_query = " OR ".join(f'"{r}"' for r in priority_roles)

        # === PASS 1: currentCompany filter (highest accuracy) ===
        if company_linkedin_id and company_linkedin_id.isdigit():
            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?currentCompany=%5B%22{company_linkedin_id}%22%5D"
                f"&keywords={quote_plus(role_query)}"
                f"&origin=FACETED_SEARCH"
            )
            logger.info(f"  👥 Pass 1: Searching people at {company_name} (company filter)...")
            found = self._execute_people_search(search_url, roles, clean_company, seen_urls, max_results, strict_company_match=False)
            people.extend(found)

        # === PASS 2: Strict boolean keyword search ===
        if len(people) < max_results:
            search_keyword = f'"{clean_company}" ({role_query})'
            encoded = quote_plus(search_keyword)
            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
            )
            remaining = max_results - len(people)
            logger.info(f"  👥 Pass 2: Searching people at {company_name} (keyword search)...")
            found = self._execute_people_search(search_url, roles, clean_company, seen_urls, remaining, strict_company_match=True)
            people.extend(found)

        # === PASS 3: Relaxed search (just company name + top role) ===
        if len(people) < max_results:
            search_keyword = f'{clean_company} {priority_roles[0] if priority_roles else "Founder"}'
            encoded = quote_plus(search_keyword)
            search_url = (
                f"https://www.linkedin.com/search/results/people/"
                f"?keywords={encoded}&origin=SWITCH_SEARCH_VERTICAL"
            )
            remaining = max_results - len(people)
            logger.info(f"  👥 Pass 3: Relaxed search at {company_name}...")
            found = self._execute_people_search(search_url, roles, clean_company, seen_urls, remaining, strict_company_match=True)
            people.extend(found)

        # Sort by role priority
        people.sort(key=lambda p: self._role_priority(p.get("title", ""), roles))

        logger.info(f"  Found {len(people)} decision makers at {company_name}")
        return people

    def _execute_people_search(
        self,
        search_url: str,
        roles: List[str],
        clean_company: str,
        seen_urls: Set[str],
        max_results: int,
        strict_company_match: bool = True,
    ) -> List[Dict[str, str]]:
        """Execute a single people search pass and return matched results."""
        people: List[Dict[str, str]] = []

        try:
            self.driver.get(search_url)
            time.sleep(random.uniform(3.0, 5.0))
            self._close_popups()

            # Wait for results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.search-results-container, ul.reusable-search__entity-result-list")
                    )
                )
            except TimeoutException:
                return []

            self._scroll_page()

            # Extract people cards
            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.reusable-search__result-container, div[data-chameleon-result-urn]"
            )

            # Build company name tokens for fuzzy matching
            company_tokens = set(clean_company.lower().split())
            # Remove very short/common words that cause false matches
            company_tokens -= {"the", "and", "of", "for", "a", "an", "in", "&"}

            for card in cards:
                if len(people) >= max_results:
                    break

                person = self._extract_person_from_card(card)
                if not person or person["linkedin_url"] in seen_urls:
                    continue

                title_lower = person.get("title", "").lower()
                raw_text = person.get("raw_text", "").lower()

                # 1. Check if their title matches target roles
                is_target = any(role.lower() in title_lower for role in roles)
                if not is_target:
                    continue

                # 2. Company match validation
                if strict_company_match:
                    # Token-based matching: at least 60% of company name words must appear
                    if company_tokens:
                        matched = sum(1 for t in company_tokens if t in raw_text)
                        match_ratio = matched / len(company_tokens)
                        if match_ratio < 0.6:
                            logger.debug(f"    Skipped (Company mismatch {match_ratio:.0%}): {person['name']} — {person['title']}")
                            continue

                seen_urls.add(person["linkedin_url"])
                people.append(person)
                logger.info(f"    ✓ Found: {person['name']} — {person['title']}")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(f"  People search error: {e}")

        return people

    # ── Card Extraction ───────────────────────────────────────────────────────

    def _extract_company_from_card(self, card) -> Optional[Dict[str, str]]:
        """Extract company info from a search result card."""
        try:
            result = {}

            # Company name and URL
            links = card.find_elements(By.CSS_SELECTOR, "a[href*='/company/']")
            for link in links:
                text = link.text.strip()
                if text:
                    result["linkedin_url"] = link.get_attribute("href").split("?")[0]
                    result["name"] = text.split("\n")[0]
                    break

            if not result.get("name"):
                return None

            # Tagline / location from raw text
            card_text = card.text.split('\n')
            lines = [
                line.strip() for line in card_text 
                if line.strip() and line.strip() != result["name"] and line.strip() != "Follow"
            ]

            result["tagline"] = lines[0] if len(lines) > 0 else ""
            result["location"] = lines[1] if len(lines) > 1 else ""

            return result

        except StaleElementReferenceException:
            return None
        except Exception as e:
            logger.debug(f"  Card extraction error: {e}")
            return None

    def _extract_person_from_card(self, card) -> Optional[Dict[str, str]]:
        """Extract person info from a search result card."""
        try:
            result = {}

            # Name and profile URL
            links = card.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
            for link in links:
                text = link.text.strip()
                if text and 'View' not in text:
                    result["linkedin_url"] = link.get_attribute("href").split("?")[0]
                    result["name"] = text.split("\n")[0]
                    break

            if not result.get("name") or result["name"] == "LinkedIn Member":
                return None

            # Title / headline — try dedicated subtitle element first
            title = ""
            for subtitle_sel in [
                "div.entity-result__primary-subtitle",
                "div.linked-area div.t-14.t-normal",
                "p.entity-result__summary",
            ]:
                try:
                    el = card.find_element(By.CSS_SELECTOR, subtitle_sel)
                    title = el.text.strip().split("\n")[0]
                    if title:
                        break
                except NoSuchElementException:
                    continue

            # Fallback: parse from raw card text
            if not title:
                card_text = card.text.split('\n')
                lines = [
                    line.strip() for line in card_text
                    if line.strip()
                    and line.strip() != result["name"]
                    and 'degree connection' not in line.lower()
                    and 'view' not in line.lower()
                    and '•' not in line
                    and line.strip() != 'Connect'
                    and line.strip() != 'Follow'
                    and line.strip() != 'Message'
                    and line.strip() != 'Pending'
                ]
                title = lines[0] if lines else ""

            result["title"] = title

            # Full raw text for company matching
            card_text = card.text.split('\n')
            result["raw_text"] = " ".join(card_text).lower()

            # Connection degree
            degree = "unknown"
            for line in card_text:
                line_l = line.strip().lower()
                if line_l == '1st' or 'st degree' in line_l:
                    degree = '1st'
                    break
                elif line_l == '2nd' or 'nd degree' in line_l:
                    degree = '2nd'
                    break
                elif line_l == '3rd' or line_l == '3rd+' or 'rd degree' in line_l:
                    degree = '3rd+'
                    break
            result["connection_degree"] = degree

            return result

        except StaleElementReferenceException:
            return None
        except Exception as e:
            logger.debug(f"  Person card extraction error: {e}")
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _role_priority(self, title: str, roles: List[str]) -> int:
        """Return priority index for a role title — lower is higher priority."""
        title_lower = title.lower()
        for idx, role in enumerate(roles):
            if role.lower() in title_lower:
                return idx
        return len(roles)  # Unknown role gets lowest priority

    def _scroll_page(self):
        """Scroll down to load lazy-loaded search results."""
        for _ in range(3):
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(g_settings.SCROLL_PAUSE)

    def _close_popups(self):
        """Dismiss common LinkedIn popups."""
        popup_selectors = [
            '//button[contains(@aria-label, "Dismiss")]',
            '//button[contains(text(), "Got it")]',
            '//button[contains(text(), "Not now")]',
            '//button[contains(text(), "Skip")]',
            '//button[contains(@class, "msg-overlay-bubble-header__control--close-btn")]',
            '//button[contains(@aria-label, "Close")]',
        ]
        for xpath in popup_selectors:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                btn.click()
                time.sleep(0.5)
            except NoSuchElementException:
                continue
            except Exception:
                continue
