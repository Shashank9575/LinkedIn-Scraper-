"""
LinkedIn Messenger — Connection Requests & DMs
================================================
Handles all outreach:
- Send connection requests with personalized notes (300 char max)
- Send DMs to accepted connections (1st degree)
- Check pending connections for follow-up
- Message personalization with Spintax support
"""

import re
import time
import random
from typing import Dict, Optional, List

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()


def resolve_spintax(text: str) -> str:
    """Resolves spintax strings like {Hi|Hello} dynamically."""
    max_iterations = 100  # Safety guard against malformed templates
    iteration = 0
    while iteration < max_iterations:
        match = re.search(r'\{([^{}]+)\}', text)
        if not match:
            break
        options = match.group(1).split('|')
        text = text[:match.start()] + random.choice(options) + text[match.end():]
        iteration += 1
    return text


def personalize_message(
    template: str,
    name: str = "",
    company: str = "",
    industry: str = "",
    title: str = "",
) -> str:
    """
    Replace placeholders and resolve Spintax in a message template.

    Placeholders: {name}, {company}, {industry}, {title}
    Spintax (use double braces in settings): {{option1|option2}}
    """
    # First, apply placeholder replacement using manual str.replace
    # to avoid crashes from curly braces in company/name values
    message = template
    message = message.replace("{name}", name or "there")
    message = message.replace("{company}", company or "your company")
    message = message.replace("{industry}", industry or "your industry")
    message = message.replace("{title}", title or "your role")

    # Convert remaining double braces to single braces for Spintax
    # Settings templates use {{Hi|Hello}} to avoid conflict with .format() style
    message = message.replace("{{", "{").replace("}}", "}")

    # Then resolve any remaining Spintax
    message = resolve_spintax(message)

    return message.strip()


class LinkedInMessenger:
    """
    Handles LinkedIn outreach — connection requests and DMs.
    Operates on the same Chrome driver as the rest of the scraper.
    """

    def __init__(self, driver):
        self.driver = driver
        self._connections_sent_today = 0
        self._dms_sent_today = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def send_connection_request(
        self, profile_url: str, note: str = "", skip_navigation: bool = False
    ) -> bool:
        """
        Send a connection request with an optional personalized note.

        Args:
            profile_url: LinkedIn profile URL of the person
            note: Personalized note (max 300 characters)
            skip_navigation: Skip navigating to profile (already there)

        Returns:
            True if connection request was sent successfully
        """
        if self._connections_sent_today >= g_settings.MAX_CONNECTIONS_PER_DAY:
            logger.warning(
                f"  ⚠ Daily connection limit reached ({g_settings.MAX_CONNECTIONS_PER_DAY})"
            )
            return False

        logger.info(f"  🤝 Sending connection request to {profile_url}...")

        try:
            # Navigate to profile if not already there
            if not skip_navigation:
                current_url = self.driver.current_url
                if profile_url.rstrip("/").split("?")[0] not in current_url:
                    self.driver.get(profile_url)
                    time.sleep(random.uniform(2.0, 4.0))
                    self._close_popups()

            # Find and click the Connect button
            connect_clicked = self._click_connect_button()
            if not connect_clicked:
                logger.warning(f"  Could not find Connect button on {profile_url}")
                return False

            time.sleep(random.uniform(1.5, 2.5))

            # Wait for the connection modal to appear
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.artdeco-modal, div[role='dialog']")
                    )
                )
            except TimeoutException:
                # Modal may not appear if LinkedIn sends directly
                pass

            # Look for the "Add a note" option in the modal
            if note:
                note_added = self._add_connection_note(note)
                if not note_added:
                    logger.warning(f"  Could not add note, sending without note")

            # Click "Send" button
            sent = self._click_send_button()
            if sent:
                self._connections_sent_today += 1
                logger.info(
                    f"  ✅ Connection request sent! ({self._connections_sent_today}/"
                    f"{g_settings.MAX_CONNECTIONS_PER_DAY} today)"
                )
                time.sleep(random.uniform(
                    g_settings.ACTION_DELAY_MIN,
                    g_settings.ACTION_DELAY_MAX
                ))
                return True
            else:
                # Fallback: try dismissing the modal to avoid blocking the next action
                try:
                    dismiss = self.driver.find_element(
                        By.XPATH, "//button[contains(@aria-label, 'Dismiss')]")
                    dismiss.click()
                except Exception:
                    pass
                logger.warning(f"  Failed to send connection request")
                return False

        except Exception as e:
            logger.error(f"  Connection request error: {e}")
            return False

    def send_dm(self, profile_url: str, message: str) -> bool:
        """
        Send a direct message to a 1st-degree connection.

        Args:
            profile_url: LinkedIn profile URL
            message: The message to send

        Returns:
            True if DM was sent successfully
        """
        if self._dms_sent_today >= g_settings.MAX_DMS_PER_DAY:
            logger.warning(
                f"  ⚠ Daily DM limit reached ({g_settings.MAX_DMS_PER_DAY})"
            )
            return False

        logger.info(f"  💬 Sending DM to {profile_url}...")

        try:
            # Navigate to profile
            current_url = self.driver.current_url
            if profile_url.rstrip("/").split("?")[0] not in current_url:
                self.driver.get(profile_url)
                time.sleep(random.uniform(2.0, 4.0))
                self._close_popups()

            # Click Message button
            msg_clicked = self._click_message_button()
            if not msg_clicked:
                logger.warning(f"  Message button not found — may not be 1st degree connection")
                return False

            time.sleep(random.uniform(2.0, 3.0))

            # Type message in the chat box
            typed = self._type_message(message)
            if not typed:
                logger.warning(f"  Could not type message")
                return False

            time.sleep(random.uniform(1.0, 2.0))

            # Click Send
            sent = self._click_dm_send_button()
            if sent:
                self._dms_sent_today += 1
                logger.info(
                    f"  ✅ DM sent! ({self._dms_sent_today}/"
                    f"{g_settings.MAX_DMS_PER_DAY} today)"
                )

                # Close the messaging overlay
                self._close_message_overlay()

                time.sleep(random.uniform(
                    g_settings.ACTION_DELAY_MIN,
                    g_settings.ACTION_DELAY_MAX
                ))
                return True
            else:
                logger.warning(f"  Failed to send DM")
                return False

        except Exception as e:
            logger.error(f"  DM sending error: {e}")
            return False

    def get_pending_connections(self) -> List[Dict[str, str]]:
        """
        Check the LinkedIn connections page for recently accepted connections.
        Returns list of dicts: {name, linkedin_url}
        """
        logger.info("  📬 Checking for recently accepted connections...")

        try:
            self.driver.get("https://www.linkedin.com/mynetwork/invite-connect/connections/")
            time.sleep(random.uniform(3.0, 5.0))
            self._close_popups()

            accepted = []

            # Look for connection cards
            cards = self.driver.find_elements(
                By.CSS_SELECTOR,
                "li.mn-connection-card, li.reusable-search__result-container, div.mn-connection-card"
            )

            for card in cards:
                try:
                    # Extract name and URL
                    link = card.find_element(By.CSS_SELECTOR, "a[href*='/in/']")
                    name_el = card.find_element(
                        By.CSS_SELECTOR,
                        "span.mn-connection-card__name, span[dir='ltr'] > span, span.t-16"
                    )
                    
                    raw_url = link.get_attribute("href").split("?")[0].rstrip("/")
                    accepted.append({
                        "name": name_el.text.strip(),
                        "linkedin_url": raw_url,
                    })
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            logger.info(f"  Found {len(accepted)} recent connections")
            return accepted

        except Exception as e:
            logger.error(f"  Error checking pending connections: {e}")
            return []

    # ── Connection Request Helpers ────────────────────────────────────────────

    def _click_connect_button(self) -> bool:
        """Find and click the 'Connect' button on a profile page."""
        # Strategy 1: Direct connect button
        for xpath in [
            "//button[contains(@aria-label, 'Connect') and not(contains(@aria-label, 'Connected'))]",
            "//button[.//span[text()='Connect']]",
            "//button[text()='Connect']",
        ]:
            try:
                btns = self.driver.find_elements(By.XPATH, xpath)
                for btn in btns:
                    if btn.is_displayed():
                        text = btn.text.strip().lower()
                        if "connect" in text and "connected" not in text and "pending" not in text:
                            try:
                                btn.click()
                            except ElementClickInterceptedException:
                                self.driver.execute_script("arguments[0].click();", btn)
                            return True
            except Exception:
                continue

        # Strategy 2: "More" button → Connect from dropdown
        for more_xpath in [
            "//button[contains(@aria-label, 'More actions')]",
            "//button[.//span[text()='More']]",
            "//button[contains(@aria-label, 'More')]",
        ]:
            try:
                more_btns = self.driver.find_elements(By.XPATH, more_xpath)
                for more_btn in more_btns:
                    if more_btn.is_displayed():
                        try:
                            more_btn.click()
                        except ElementClickInterceptedException:
                            self.driver.execute_script("arguments[0].click();", more_btn)
                        time.sleep(1.5)

                        connect_options = self.driver.find_elements(
                            By.XPATH,
                            "//div[contains(@class, 'artdeco-dropdown__content')]//span[text()='Connect'] | //div[contains(@class, 'artdeco-dropdown__content')]//div[contains(text(), 'Connect')]"
                        )
                        for option in connect_options:
                            if option.is_displayed():
                                try:
                                    option.click()
                                except ElementClickInterceptedException:
                                    self.driver.execute_script("arguments[0].click();", option)
                                return True
            except Exception:
                pass

        return False

    def _add_connection_note(self, note: str) -> bool:
        """Add a personalized note to the connection request modal."""
        # Truncate to 300 characters (LinkedIn limit)
        note = note[:300]

        try:
            # Click "Add a note" button
            add_note_btn = None
            for xpath in [
                "//button[contains(@aria-label, 'Add a note')]",
                "//button[.//span[text()='Add a note']]",
                "//button[text()='Add a note']",
            ]:
                try:
                    add_note_btn = self.driver.find_element(By.XPATH, xpath)
                    break
                except NoSuchElementException:
                    continue

            if add_note_btn:
                add_note_btn.click()
                time.sleep(1.0)

            # Find the note textarea
            textarea = None
            for selector in [
                "textarea[name='message']",
                "textarea#custom-message",
                "textarea[placeholder*='Add a note']",
                "textarea",
            ]:
                try:
                    textarea = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if textarea.is_displayed():
                        break
                    textarea = None
                except NoSuchElementException:
                    continue

            if not textarea:
                return False

            # Clear and type the note
            textarea.clear()
            time.sleep(0.5)

            # Type slowly for human-like behavior
            for char in note:
                textarea.send_keys(char)
                time.sleep(random.uniform(0.02, 0.08))

            return True

        except Exception as e:
            logger.debug(f"  Add note error: {e}")
            return False

    def _click_send_button(self) -> bool:
        """Click the Send button in the connection request modal."""
        for xpath in [
            "//button[contains(@aria-label, 'Send')]",
            "//button[.//span[text()='Send']]",
            "//button[text()='Send']",
            "//button[contains(@aria-label, 'Send invitation')]",
            "//button[.//span[text()='Send invitation']]",
            "//div[contains(@class, 'artdeco-modal')]//button[contains(@class, 'artdeco-button--primary')]",
        ]:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    try:
                        btn.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2.0)
                    return True
            except NoSuchElementException:
                continue
        return False

    # ── DM Helpers ────────────────────────────────────────────────────────────

    def _click_message_button(self) -> bool:
        """Click the 'Message' button on a profile page."""
        for xpath in [
            "//button[contains(@aria-label, 'Message')]",
            "//button[.//span[text()='Message']]",
            "//button[text()='Message']",
            "//a[contains(@href, '/messaging/')]",
        ]:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    try:
                        btn.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", btn)
                    return True
            except NoSuchElementException:
                continue
        return False

    def _type_message(self, message: str) -> bool:
        """Type a message in the messaging chat box."""
        try:
            # Wait for messaging overlay to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.msg-form__contenteditable, div[role='textbox']")
                    )
                )
            except TimeoutException:
                logger.warning("  Messaging overlay did not appear")
                return False

            # Find the message input
            msg_box = None
            for selector in [
                "div.msg-form__contenteditable[contenteditable='true']",
                "div[role='textbox'][contenteditable='true']",
                "div.msg-form__msg-content-container div[contenteditable='true']",
            ]:
                try:
                    msg_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if msg_box.is_displayed():
                        break
                    msg_box = None
                except NoSuchElementException:
                    continue

            if not msg_box:
                return False

            # Click to focus
            msg_box.click()
            time.sleep(0.5)

            # Type message line by line with human-like delays
            lines = message.split("\n")
            for i, line in enumerate(lines):
                for char in line:
                    msg_box.send_keys(char)
                    time.sleep(random.uniform(0.01, 0.05))

                # Add newline (Shift+Enter for new line without sending)
                if i < len(lines) - 1:
                    ActionChains(self.driver).key_down(Keys.SHIFT).send_keys(
                        Keys.ENTER
                    ).key_up(Keys.SHIFT).perform()
                    time.sleep(0.1)

            return True

        except Exception as e:
            logger.debug(f"  Type message error: {e}")
            return False

    def _click_dm_send_button(self) -> bool:
        """Click the send button in the messaging overlay."""
        for xpath in [
            "//button[contains(@class, 'msg-form__send-button')]",
            "//button[contains(@aria-label, 'Send')]",
            "//button[text()='Send']",
            "//button[.//span[text()='Send']]",
        ]:
            try:
                btn = self.driver.find_element(By.XPATH, xpath)
                if btn.is_displayed() and btn.is_enabled():
                    try:
                        btn.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2.0)
                    return True
            except NoSuchElementException:
                continue
        return False

    def _close_message_overlay(self):
        """Close the messaging overlay after sending a DM."""
        try:
            close_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                "button[data-control-name='overlay.close_conversation_window'],"
                "button.msg-overlay-bubble-header__control--close-btn,"
                "button[aria-label*='Close your conversation']"
            )
            close_btn.click()
            time.sleep(1.0)
        except NoSuchElementException:
            pass
        except Exception:
            pass

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
