# LinkedIn Lead Generator

Automated LinkedIn scraper & outreach tool for finding business founders and marketing managers who may need influencer marketing services.

## 🎯 What It Does

1. **Search by Industry** — Finds companies across Tech, Fashion, Beauty, Fitness, E-commerce, etc.
2. **Scrape Company Profiles** — Extracts company details, website, Instagram handle
3. **Find Contact Info** — Discovers emails from company websites
4. **Find Decision Makers** — Locates Founders, CEOs, CMOs, Marketing Managers
5. **Send Connection Requests** — Personalized notes (300 char max)
6. **Follow-Up DMs** — Sends full pitch to accepted connections

## 📦 Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy the `.env.example` file to `.env` and edit it with your LinkedIn login:

```env
LI_USERNAME_1=your_email@example.com
LI_PASSWORD_1=your_password
```

For multi-account rotation:
```env
LI_USERNAME_1=email1@example.com
LI_PASSWORD_1=password1
LI_USERNAME_2=email2@example.com
LI_PASSWORD_2=password2
```

### 3. Customize Settings

Edit `config/settings.py` to change:
- Target industries & search keywords
- Decision maker roles
- DM templates (with Spintax support)
- Rate limits & delays
- Max companies per industry

## 🚀 Usage

### Using START.bat (Windows — Interactive)

Double-click `START.bat` and follow the prompts.

### Using Command Line

```bash
# Full pipeline — search, connect, and DM
python main.py

# Search specific industries
python main.py --industries "Technology & SaaS" "Fashion & Apparel"

# Search only (no outreach)
python main.py --mode search

# Send connection requests only
python main.py --mode connect

# Follow up — DM accepted connections
python main.py --mode followup

# Limit companies per industry
python main.py --max-companies 50

# Verify setup without scraping
python main.py --dry-run

# Clear previous progress and start fresh
python main.py --reset-checkpoint
```

## 📊 Output

Results are saved to `data/linkedin_leads.csv` with these columns:

| Column | Description |
|--------|-------------|
| `company_name` | Business name |
| `industry` | Business category |
| `company_linkedin_url` | LinkedIn company page URL |
| `website` | Company website |
| `company_size` | Employee range |
| `location` | HQ location |
| `email` | Contact email |
| `instagram` | Instagram handle |
| `decision_maker_name` | Founder / CMO name |
| `decision_maker_title` | Their role |
| `decision_maker_linkedin` | Their LinkedIn profile URL |
| `connection_status` | pending / connected / not_sent |
| `dm_sent` | True / False |
| `dm_message` | The message that was sent |
| `source_keyword` | Which search keyword found them |

## ⚠️ Important Safety Notes

- **Rate Limits**: The tool has built-in safety limits (20 connections/day, 60 profile views/day). Do NOT increase these.
- **Human-Like Behavior**: All actions include random delays (30-90s) to mimic human behavior.
- **Account Safety**: Use dedicated LinkedIn accounts. Your main account may get restricted.
- **Manual Login Fallback**: If automated login fails, the tool will open a browser for manual login.
- **Session Persistence**: Cookies are saved so you don't need to re-login every time.
- **Resume Capability**: If interrupted, the tool resumes from where it left off.

## 📁 Project Structure

```
linkedin_scraper/
├── main.py                    # CLI entry point
├── START.bat                  # Windows batch launcher
├── requirements.txt           # Python dependencies
├── .env.example               # LinkedIn credentials template
├── config/
│   └── settings.py            # All configurable settings
├── core/
│   ├── scraper.py             # Main orchestrator
│   ├── linkedin_search.py     # Company & people search
│   ├── company_fetcher.py     # Company profile scraper
│   ├── people_finder.py       # Decision maker finder
│   └── messenger.py           # Connection requests & DMs
├── utils/
│   ├── logger.py              # Colored console + file logging
│   ├── exporter.py            # CSV export with deduplication
│   └── proxy_util.py          # Proxy Chrome extension
├── data/                      # Output CSVs (auto-created)
└── logs/                      # Log files (auto-created)
```

## 🔄 DM Templates

The tool includes industry-specific DM templates with **Spintax** support:

```
{{Hey|Hi|Hello}} {name}! 👋

Thanks for connecting! I'm reaching out because {company} caught my eye...
```

- `{name}` → Decision maker's first name
- `{company}` → Company name
- `{industry}` → Industry category
- `{{option1|option2}}` → Random selection

Customize templates in `config/settings.py`.
