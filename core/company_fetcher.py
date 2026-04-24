"""
Company Profile Fetcher
========================
Visits a LinkedIn company page and extracts detailed information:
- Name, industry, size, location, description
- Website URL
- Instagram handle (from linked social accounts)
- Contact email (from company website)
"""

import re
import time
import random
import requests
from typing import Dict, Optional, List
from urllib.parse import urlparse

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


class CompanyFetcher:
    """
    Visits LinkedIn company pages and extracts detailed info.
    Operates on the same Chrome driver used for login and search.
    """

    def __init__(self, driver):
        self.driver = driver
        self._request_count = 0

    def total_requests(self) -> int:
        return self._request_count

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch(self, company_url: str, source_keyword: str = "") -> Optional[Dict]:
        """
        Visit a LinkedIn company page and extract all available info.

        Args:
            company_url: LinkedIn company page URL
            source_keyword: The search keyword that found this company

        Returns:
            Dict with company data, or None if scrape fails
        """
        # Normalize URL — make sure we're on the about page
        about_url = company_url.rstrip("/")
        if not about_url.endswith("/about"):
            about_url += "/about"

        logger.info(f"  📊 Visiting company: {company_url}")

        try:
            self.driver.get(about_url)
            self._request_count += 1
            time.sleep(random.uniform(3.0, 5.0))
            self._close_popups()
            
            # Follow company if possible
            self._follow_company()
            
        except Exception as e:
            logger.error(f"  Could not load company page: {e}")
            return None

        data = {
            "company_linkedin_url": company_url.rstrip("/"),
            "source_keyword": source_keyword,
        }

        # Extract company name
        data["company_name"] = self._extract_company_name()
        if not data["company_name"]:
            logger.warning(f"  Could not extract company name from {company_url}")
            return None

        # Extract about section fields
        data.update(self._extract_about_fields())

        # Extract website
        data["website"] = self._extract_website()

        # Extract Instagram handle
        if g_settings.EXTRACT_INSTAGRAM:
            data["instagram"] = self._extract_instagram()

        # Extract email from company website
        if g_settings.SCRAPE_COMPANY_WEBSITE and data.get("website"):
            data["email"] = self._extract_email_from_website(data["website"])
        else:
            data["email"] = ""

        # Extract numeric company ID for accurate people search
        data["company_numeric_id"] = self._extract_company_id()

        logger.info(
            f"  ✓ {data['company_name']} | "
            f"{data.get('industry', '?')} | "
            f"{data.get('company_size', '?')} employees | "
            f"Web: {data.get('website', 'N/A')}"
        )

        return data

    # ── Field Extraction ──────────────────────────────────────────────────────

    def _extract_company_name(self) -> str:
        """Extract company name from the page."""
        for selector in [
            "h1.org-top-card-summary__title",
            "h1[class*='org-top-card']",
            "h1.top-card-layout__title",
            "h1",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                name = el.text.strip()
                if name:
                    return name
            except NoSuchElementException:
                continue
        return ""

    def _extract_company_id(self) -> str:
        """Extract the numeric LinkedIn company ID from the page for precise filtering."""
        import re
        # Method 1: Check data attributes on the page
        for selector in [
            "[data-company-id]",
            "[data-entity-urn]",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                attr = el.get_attribute("data-company-id") or el.get_attribute("data-entity-urn") or ""
                match = re.search(r'(\d{5,})', attr)
                if match:
                    return match.group(1)
            except NoSuchElementException:
                continue

        # Method 2: Look for company ID in the page source (common LinkedIn pattern)
        try:
            page_source = self.driver.page_source
            # LinkedIn embeds companyId in JSON-LD or inline scripts
            patterns = [
                r'"companyId"\s*:\s*(\d+)',
                r'"objectUrn"\s*:\s*"urn:li:company:(\d+)"',
                r'urn:li:fs_normalized_company:(\d+)',
                r'urn:li:company:(\d+)',
                r'/company/(\d+)/',
            ]
            for pattern in patterns:
                match = re.search(pattern, page_source)
                if match:
                    return match.group(1)
        except Exception:
            pass

        return ""

    def _extract_about_fields(self) -> Dict:
        """Extract industry, size, location, description from the About section."""
        fields = {
            "industry": "",
            "company_size": "",
            "location": "",
            "description": "",
        }

        # Try to extract from structured about section (dt/dd pairs)
        try:
            dt_elements = self.driver.find_elements(By.CSS_SELECTOR, "dl.overflow-hidden dt")
            dd_elements = self.driver.find_elements(By.CSS_SELECTOR, "dl.overflow-hidden dd")

            for dt, dd in zip(dt_elements, dd_elements):
                label = dt.text.strip().lower()
                value = dd.text.strip()

                if "industry" in label:
                    fields["industry"] = value
                elif "company size" in label or "size" in label:
                    fields["company_size"] = value
                elif "headquarters" in label or "location" in label:
                    fields["location"] = value

        except (NoSuchElementException, StaleElementReferenceException):
            pass

        # Fallback: try other selectors for individual fields
        if not fields["industry"]:
            for sel in [
                "div[data-test-id='about-us__industry'] dd",
                "div.org-top-card-summary-info-list__info-item",
            ]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    fields["industry"] = el.text.strip()
                    break
                except NoSuchElementException:
                    continue

        if not fields["location"]:
            for sel in [
                "div[data-test-id='about-us__headquarters'] dd",
                "div.org-top-card-summary-info-list__info-item:last-child",
            ]:
                try:
                    el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    if text and len(text) > 2:
                        fields["location"] = text
                    break
                except NoSuchElementException:
                    continue

        # Company description / overview
        try:
            desc_el = self.driver.find_element(
                By.CSS_SELECTOR,
                "section.org-about-module p, p[data-test-id='about-us__description']"
            )
            fields["description"] = desc_el.text.strip()[:500]  # Limit length
        except NoSuchElementException:
            pass

        return fields

    def _extract_website(self) -> str:
        """Extract company website URL."""
        for selector in [
            "a[data-test-id='about-us__website'] span",
            "a[data-test-id='about-us__website']",
            "a[href*='http'][class*='link-without-visited-state']",
            "dd a[href^='http']",
        ]:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, selector)
                href = el.get_attribute("href") or el.text.strip()
                if href and "linkedin.com" not in href:
                    return href
            except NoSuchElementException:
                continue

        # Fallback: look for website in page text
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Find URLs within the page text
            urls = re.findall(
                r'https?://(?:www\.)?[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?',
                page_text
            )
            for url in urls:
                if "linkedin.com" not in url and "licdn.com" not in url:
                    return url
        except Exception:
            pass

        return ""

    def _extract_instagram(self) -> str:
        """Try to find Instagram handle from linked social accounts or about text."""
        # Method 1: Look for Instagram links on the page
        try:
            ig_links = self.driver.find_elements(
                By.CSS_SELECTOR,
                "a[href*='instagram.com']"
            )
            for link in ig_links:
                href = link.get_attribute("href") or ""
                if "instagram.com" in href:
                    # Extract username from URL
                    match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', href)
                    if match:
                        return f"@{match.group(1)}"
        except Exception:
            pass

        # Method 2: Search page text for Instagram mentions
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            patterns = [
                r'@([a-zA-Z0-9_.]{3,30})\s*(?:on\s+)?(?:Instagram|IG)',
                r'(?:Instagram|IG)\s*[:\-]?\s*@?([a-zA-Z0-9_.]{3,30})',
                r'instagram\.com/([a-zA-Z0-9_.]{3,30})',
            ]
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return f"@{match.group(1)}"
        except Exception:
            pass

        return ""

    def _extract_email_from_website(self, website_url: str) -> str:
        """
        Visit the company website and look for contact email addresses.
        Uses requests (not Selenium) for speed.
        """
        if not website_url:
            return ""

        logger.debug(f"  Checking website for email: {website_url}")

        try:
            # Try the main page and common contact pages
            pages_to_check = [
                website_url,
                website_url.rstrip("/") + "/contact",
                website_url.rstrip("/") + "/contact-us",
                website_url.rstrip("/") + "/about",
            ]

            for page_url in pages_to_check:
                try:
                    resp = requests.get(
                        page_url,
                        timeout=10,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                        },
                        verify=False,
                    )
                    if resp.status_code == 200:
                        emails = self._find_emails_in_text(resp.text)
                        if emails:
                            # Prefer info@, contact@, hello@ over others
                            priority_prefixes = ["info@", "contact@", "hello@", "team@", "support@"]
                            for prefix in priority_prefixes:
                                for email in emails:
                                    if email.startswith(prefix):
                                        return email
                            return emails[0]  # Return first found
                except requests.RequestException:
                    continue

        except Exception as e:
            logger.debug(f"  Email extraction failed: {e}")

        return ""

    def _find_emails_in_text(self, text: str) -> List[str]:
        """Extract email addresses from text using regex."""
        # Standard email pattern
        pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(pattern, text)

        # Filter out common false positives
        filtered = []
        skip_patterns = [
            "example.com", "email.com", "domain.com", "yourcompany.com",
            "sentry.io", "wixpress.com", "cloudflare.com",
            ".png", ".jpg", ".gif", ".svg", ".webp",
        ]
        for email in emails:
            email_lower = email.lower()
            if not any(skip in email_lower for skip in skip_patterns):
                filtered.append(email_lower)

        # Remove duplicates while maintaining order
        seen = set()
        unique = []
        for email in filtered:
            if email not in seen:
                seen.add(email)
                unique.append(email)

        return unique

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

    def _follow_company(self):
        """Click the Follow button on the company page if present."""
        for xpath in [
            "//button[contains(@aria-label, 'Follow')]",
            "//button[.//span[text()='Follow']]",
            "//button[text()='Follow']",
        ]:
            try:
                btns = self.driver.find_elements(By.XPATH, xpath)
                for btn in btns:
                    if btn.is_displayed():
                        text = btn.text.strip().lower()
                        if "follow" in text and "following" not in text:
                            try:
                                btn.click()
                                logger.info("  ✓ Followed company")
                                time.sleep(1.0)
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", btn)
                                logger.info("  ✓ Followed company (JS)")
                                time.sleep(1.0)
                            return
            except Exception:
                continue
