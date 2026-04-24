"""
LinkedIn Lead Generator — Configuration Settings
===================================================
Edit this file or use .env to change scraping behaviour.
"""
import os
from dotenv import load_dotenv

# Load variables from .env file into os.environ
load_dotenv()

# ─── Operation Mode ──────────────────────────────────────────────────────────
# "search"   → search & scrape only (no outreach)
# "connect"  → send connection requests to scraped leads
# "followup" → DM accepted connections with full pitch
# "full"     → search → connect → followup (all-in-one)
OPERATION_MODE = "full"

# ─── Target Industries / Business Categories ─────────────────────────────────

INDUSTRIES = [
    "Technology & SaaS",
    "Fashion & Apparel",
    "Beauty & Skincare",
    "Fitness & Health",
    "E-commerce & D2C",
    "Food & Beverage",
    "Real Estate",
    "Education & EdTech",
    "Travel & Hospitality",
]

# Industry-specific LinkedIn search keywords
INDUSTRY_KEYWORDS = {
    "Technology & SaaS": [
        "tech startup", "SaaS company", "software company",
        "AI startup", "mobile app company", "fintech",
    ],
    "Fashion & Apparel": [
        "fashion brand", "clothing brand", "streetwear brand",
        "sustainable fashion", "fashion startup", "apparel company",
    ],
    "Beauty & Skincare": [
        "skincare brand", "beauty brand", "cosmetics company",
        "clean beauty", "beauty startup", "haircare brand",
    ],
    "Fitness & Health": [
        "fitness brand", "health and wellness", "supplement company",
        "activewear brand", "gym chain", "wellness startup",
    ],
    "E-commerce & D2C": [
        "D2C brand", "ecommerce startup", "online store",
        "direct to consumer", "ecommerce brand", "marketplace startup",
    ],
    "Food & Beverage": [
        "food brand", "beverage company", "snack brand",
        "organic food", "food startup", "healthy food brand",
    ],
    "Real Estate": [
        "real estate company", "proptech startup", "real estate agency",
        "property developer", "real estate brand",
    ],
    "Education & EdTech": [
        "edtech startup", "online education", "learning platform",
        "education company", "e-learning brand",
    ],
    "Travel & Hospitality": [
        "travel company", "hospitality brand", "hotel chain",
        "travel startup", "tourism brand",
    ],
}

# ─── Decision Maker Roles (priority order) ───────────────────────────────────

TARGET_ROLES = [
    "Founder",
    "Co-Founder",
    "CEO",
    "Chief Executive Officer",
    "CMO",
    "Chief Marketing Officer",
    "VP Marketing",
    "Vice President of Marketing",
    "Head of Marketing",
    "Marketing Director",
    "Director of Marketing",
    "Marketing Manager",
    "Growth Lead",
    "Head of Growth",
    "Brand Manager",
]

# ─── Scraping Limits ─────────────────────────────────────────────────────────

MAX_COMPANIES_PER_INDUSTRY = 20       # Max companies to scrape per industry
MAX_PEOPLE_PER_COMPANY = 3            # Max decision makers to find per company
MAX_PROFILES_PER_DAY = 60             # LinkedIn daily profile view safety limit
MAX_CONNECTIONS_PER_DAY = 20          # LinkedIn daily connection request limit
MAX_DMS_PER_DAY = 30                  # LinkedIn daily DM limit
MAX_SEARCH_PAGES = 5                  # Max search result pages to scan

# ─── Timing & Delays (seconds) ───────────────────────────────────────────────

PROFILE_VIEW_DELAY_MIN = 25.0         # Wait between profile visits
PROFILE_VIEW_DELAY_MAX = 55.0

SEARCH_DELAY_MIN = 15.0               # Wait between search page loads
SEARCH_DELAY_MAX = 30.0

ACTION_DELAY_MIN = 40.0               # Wait between actions (connect, DM)
ACTION_DELAY_MAX = 90.0

INDUSTRY_DELAY_MIN = 60.0             # Wait between industry searches
INDUSTRY_DELAY_MAX = 120.0

SCROLL_PAUSE = 2.5                    # Pause between scrolls
MAX_SCROLLS = 30                      # Max scroll attempts per page

# ─── Output ──────────────────────────────────────────────────────────────────

OUTPUT_DIR      = "data"
OUTPUT_CSV      = "data/linkedin_leads.csv"
CHECKPOINT_FILE = "data/checkpoint.json"

# ─── LinkedIn Login ──────────────────────────────────────────────────────────
# Multi-Account Login & Rotation (same pattern as Instagram scraper)
#   LI_USERNAME_1 = "email1@example.com" | LI_PASSWORD_1 = "pwd1"
#   LI_USERNAME_2 = "email2@example.com" | LI_PASSWORD_2 = "pwd2"

ACCOUNTS = []
_idx = 1
while True:
    u = os.environ.get(f"LI_USERNAME_{_idx}") or os.environ.get(f"LI_USER_{_idx}")
    p = os.environ.get(f"LI_PASSWORD_{_idx}") or os.environ.get(f"LI_PASS_{_idx}")
    if not u or not p:
        break
    ACCOUNTS.append({
        "username": u.strip().strip('"').strip("'"),
        "password": p.strip().strip('"').strip("'"),
    })
    _idx += 1

# Fallback to legacy single-account if no numbered accounts found
if not ACCOUNTS:
    _legacy_u = os.environ.get("LI_USERNAME", "").strip().strip('"').strip("'")
    _legacy_p = os.environ.get("LI_PASSWORD", "").strip().strip('"').strip("'")
    if _legacy_u and _legacy_p:
        ACCOUNTS.append({"username": _legacy_u, "password": _legacy_p})

# ─── Connection Request Note (MAX 300 characters!) ──────────────────────────
# Placeholders: {name}, {company}, {industry}
# Spintax: {{option1|option2|option3}}

CONNECTION_NOTE = """{{Hi|Hey|Hello}} {name}, I {{noticed|came across}} {company} — {{impressive|great}} work in {industry}! We connect brands with top influencers for authentic collaborations. Would love to explore a partnership. Let's connect!"""

# ─── Follow-Up DM Templates (sent after connection accepted) ────────────────
# Placeholders: {name}, {company}, {industry}, {title}
# Use DOUBLE braces for Spintax: {{option1|option2}}

DM_TEMPLATES = {
    "default": """{{Hey|Hi|Hello}} {name}! 👋

Thanks for connecting! I'm reaching out because {company} caught my eye — you're doing {{great|amazing|impressive}} work in {industry}.

We work with 500+ verified influencers across {industry} — from micro (10K) to macro (1M+) creators. Our clients typically see 3-5x ROI on influencer campaigns.

{{Would you be open to|Can we schedule}} a quick 15-min call to see if there's a fit?

Happy to share case studies from similar {industry} brands! 🚀

Best regards""",

    "Technology & SaaS": """{{Hey|Hi|Hello}} {name}! 👋

Congrats on what you're building at {company}! 🚀

I help tech brands {{amplify their reach|boost visibility|grow awareness}} through strategic influencer partnerships. We have 200+ tech creators who regularly review products, do tutorials, and create authentic content.

Some of our tech clients saw 40%+ increase in sign-ups after influencer campaigns.

{{Worth a quick chat|Open to a 15-min call}} to see if we can help {company} grow? I can share relevant case studies!

Best""",

    "Fashion & Apparel": """{{Hey|Hi|Hello}} {name}! 👋

Love what {company} is doing in fashion! 🔥

We specialize in connecting fashion brands with {{style influencers|fashion creators|lifestyle content creators}} who can authentically showcase your pieces to engaged audiences.

From lookbooks to try-on hauls, our creators drive real conversions — not just vanity metrics.

Would love to explore a collab! {{Free to chat|Can we hop on a call}} this week?

Best""",

    "Beauty & Skincare": """{{Hey|Hi|Hello}} {name}! 👋

{company}'s products look {{incredible|stunning|amazing}}! ✨

We work closely with beauty & skincare influencers who create authentic reviews, tutorials, and unboxing content. Our beauty clients see an average 4x ROI on creator partnerships.

Would you be interested in exploring an influencer campaign for {company}? I'd love to share some ideas!

Best""",

    "Fitness & Health": """{{Hey|Hi|Hello}} {name}! 💪

{company} is doing {{incredible|great|awesome}} work in the fitness space!

We have a network of fitness creators — from gym influencers to wellness coaches — who create workout content, product reviews, and transformation stories.

Our fitness brand partners typically see 3-5x ROI. Would you be open to a quick chat about how influencer marketing could help {company}?

Best""",
}

# ─── Feature Toggles ────────────────────────────────────────────────────────

SEND_CONNECTION_REQUESTS = True       # Send connection requests to decision makers
SEND_DMS = True                       # Send follow-up DMs to accepted connections
SCRAPE_COMPANY_WEBSITE = True         # Visit company website for email extraction
EXTRACT_INSTAGRAM = True              # Try to find Instagram handles

# ─── Selenium Settings ──────────────────────────────────────────────────────

HEADLESS = False                      # Keep visible for debugging / manual login

# ─── Proxy Settings ─────────────────────────────────────────────────────────

USE_PROXY = os.environ.get("USE_PROXY", "False").lower() == "true"
PROXY_HOST = os.environ.get("PROXY_HOST", "")
PROXY_PORT = os.environ.get("PROXY_PORT", "")
PROXY_USER = os.environ.get("PROXY_USER", "")
PROXY_PASS = os.environ.get("PROXY_PASS", "")
