# LinkedIn Lead Generator — Complete Execution Flow

This document outlines the step-by-step execution flow of the LinkedIn Lead Generator. You can use this as a checklist to verify each stage of the automation while testing.

## 1. Initialization & Configuration (`main.py` / `START.bat`)
- **Argument Parsing:** Reads the selected mode (`full`, `search`, `connect`, `followup`) and target industries from the command line or `START.bat`.
- **Environment Load:** Loads target industries, search limits, and LinkedIn credentials from `config/settings.py` and `.env`.
- **Browser Launch:** Initializes `undetected-chromedriver` (with or without proxy depending on settings).

## 2. Authentication (`core/scraper.py -> _linkedin_login`)
- **Cookie Check:** Looks for `li_cookies_*.json` for the current account. If found, injects cookies to bypass login.
- **Automated Login:** If cookies are missing/expired, navigates to the login page and types credentials like a human.
- **Security Challenge Check:** If LinkedIn triggers a CAPTCHA or security checkpoint, pauses for 120 seconds to allow you to manually solve it.
- **Manual Fallback:** If automated login fails or no credentials exist, prompts you in the terminal to log in manually and press ENTER when done.
- **Save Session:** Successfully verified cookies are saved back to the JSON file.

## 3. Industry Orchestration (`core/scraper.py -> run`)
- Loops through the selected target industries one by one.
- Fetches the associated `INDUSTRY_KEYWORDS` (e.g., "tech startup", "SaaS company") from settings.

## 4. Company Search (`core/linkedin_search.py -> search_companies`)
- Generates a LinkedIn Company Search URL using the industry keyword.
- **Page Navigation:** Scans results page by page (up to `MAX_SEARCH_PAGES`), scrolling down to load lazy-loaded elements.
- **Extraction:** Identifies company cards using CSS selectors (`reusable-search__result-container` or `search-entity-media`).
- **Deduplication:** Skips companies that have already been processed in `checkpoint.json`.

## 5. Company Profiling (`core/company_fetcher.py -> fetch`)
- **About Page Navigation:** Visits `linkedin.com/company/{name}/about`.
- **Data Extraction:** Scrapes the company Name, Industry, Size, Location, and Description.
- **Website & Socials:** Extracts the company Website URL and searches the page for an Instagram handle.
- **Email Extraction (External):** If `SCRAPE_COMPANY_WEBSITE` is true, sends an invisible `requests` call to the company's website (home, /contact, /about) to find public email addresses using Regex.

## 6. Decision Maker Discovery (`core/linkedin_search.py` & `core/people_finder.py`)
- **People Search (Primary Method):** Uses LinkedIn's People search by combining the `company_name` and priority target roles (e.g., `"Apple" AND ("Founder" OR "CEO")`).
- **Company People Tab (Fallback):** If the search yields 0 results, visits the company's `/people/` tab, types roles in the filter box, and extracts matching employees.
- **Filtering:** Filters the found employees against `TARGET_ROLES` to ensure they are actually decision makers.

## 7. People Profiling & Connection (`core/people_finder.py` & `core/messenger.py`)
- **Profile Visit:** Navigates to the selected decision maker's LinkedIn profile.
- **Extraction:** Scrapes Name, Title, Location, and Connection Degree.
- **Connection Request:** If `SEND_CONNECTION_REQUESTS` is enabled and a "Connect" button is available:
  - Generates a personalized note using the Spintax template (`CONNECTION_NOTE`) in settings.
  - Clicks "Connect" → "Add a note" → Types the message with random human-like delays → Clicks "Send".
  - Logs the `connection_status` as `sent`.
- **Direct DM:** If the person is already a 1st-degree connection, it skips the request and directly sends a DM.

## 8. Rate Limiting & Account Rotation (`core/scraper.py`)
- **Human-like Delays:** Implements randomized pauses (`PROFILE_VIEW_DELAY`, `ACTION_DELAY`) between actions.
- **Limits Enforcement:** Tracks how many profiles, connections, and DMs have been processed in the current session.
- **Account Rotation:** If `MAX_PROFILES_PER_DAY` is reached for an account, it deletes cookies, switches to the next configured account in `.env`, and logs in again to continue scraping without interruption.

## 9. Data Saving & Export (`utils/exporter.py`)
- **CSV Logging:** Instantly writes the completed lead (Company Data + Decision Maker Data) into `data/linkedin_leads.csv`.
- **Backups:** Automatically backs up the previous CSV file before appending new data to prevent accidental loss.
- **Checkpointing:** Saves progress (seen companies, sent requests count) into `data/checkpoint.json` so if the script crashes, it resumes exactly where it left off.

## 10. Follow-up Mode (`core/messenger.py -> run_followup`)
*(Note: This only runs if `Followup` mode is explicitly selected in START.bat)*
- Navigates to `linkedin.com/mynetwork/invite-connect/connections/`.
- Extracts a list of recently accepted connections.
- Cross-references these accepted connections with the `linkedin_leads.csv` to find records where `connection_status == "sent"` and `dm_sent == False`.
- Generates a highly personalized, industry-specific pitch from `DM_TEMPLATES` using Spintax.
- Visits the profile, clicks "Message", types the pitch, and sends.
- Updates the CSV record marking `dm_sent = True` and recording the message snippet.
