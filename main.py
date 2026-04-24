"""
LinkedIn Lead Generator — Main Entry Point
=============================================
Automated LinkedIn scraper to find business founders & marketing managers
who may need influencer marketing services.

Usage examples:
    python main.py                                          # full pipeline
    python main.py --industries "Technology & SaaS" "Fashion & Apparel"
    python main.py --mode search                            # search only (no DMs)
    python main.py --mode connect                           # connect only
    python main.py --mode followup                          # DM accepted connections
    python main.py --max-companies 50                       # limit per industry
    python main.py --dry-run                                # verify setup only
    python main.py --reset-checkpoint                       # start fresh
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent))

import config.settings as settings
from core.scraper import LinkedInScraper
from utils.exporter import CSVExporter
from utils.logger import get_logger

logger = get_logger()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LinkedIn Lead Generator — Find Founders for Influencer Marketing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--industries", nargs="+", default=None, metavar="IND",
        help="Industries to target (e.g., 'Technology & SaaS' 'Fashion & Apparel')"
    )
    p.add_argument(
        "--mode",
        choices=["full", "search", "connect", "followup"],
        default=settings.OPERATION_MODE,
        help="Operation mode: full, search (no DMs), connect (requests only), followup (DM accepted)"
    )
    p.add_argument(
        "--output", default=settings.OUTPUT_CSV,
        help="Output CSV path"
    )
    p.add_argument(
        "--max-companies", type=int, default=settings.MAX_COMPANIES_PER_INDUSTRY,
        help="Max companies per industry"
    )
    p.add_argument(
        "--max-connections", type=int, default=settings.MAX_CONNECTIONS_PER_DAY,
        help="Max connection requests per day"
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Test setup without scraping"
    )
    p.add_argument(
        "--reset-checkpoint", action="store_true",
        help="Clear resume state and start fresh"
    )
    return p.parse_args()


def apply_overrides(args):
    settings.MAX_COMPANIES_PER_INDUSTRY = args.max_companies
    settings.MAX_CONNECTIONS_PER_DAY = args.max_connections
    settings.OUTPUT_CSV = args.output
    settings.OPERATION_MODE = args.mode

    if args.industries:
        INDUSTRY_MAP = {
            "Technology_SaaS": "Technology & SaaS",
            "Fashion_Apparel": "Fashion & Apparel",
            "Beauty_Skincare": "Beauty & Skincare",
            "Fitness_Health": "Fitness & Health",
            "Ecommerce_D2C": "E-commerce & D2C",
            "Food_Beverage": "Food & Beverage",
            "RealEstate": "Real Estate",
            "Education_EdTech": "Education & EdTech",
            "Travel_Hospitality": "Travel & Hospitality",
        }
        # Clean up industry names
        cleaned = []
        for ind in args.industries:
            ind = ind.strip()
            if ind in INDUSTRY_MAP:
                cleaned.append(INDUSTRY_MAP[ind])
            else:
                cleaned.append(ind)
        settings.INDUSTRIES = cleaned

    if args.mode == "search":
        settings.SEND_CONNECTION_REQUESTS = False
        settings.SEND_DMS = False
    elif args.mode == "connect":
        settings.SEND_CONNECTION_REQUESTS = True
        settings.SEND_DMS = False
    elif args.mode == "full":
        settings.SEND_CONNECTION_REQUESTS = True
        settings.SEND_DMS = True

    if args.reset_checkpoint:
        cp = Path(settings.CHECKPOINT_FILE)
        if cp.exists():
            cp.unlink()
            logger.info("Checkpoint cleared")


def dry_run():
    logger.info("=== DRY RUN ===")
    logger.info(f"Operation mode  : {settings.OPERATION_MODE.upper()}")
    logger.info(f"Industries      : {settings.INDUSTRIES}")
    logger.info(f"Max companies   : {settings.MAX_COMPANIES_PER_INDUSTRY}/industry")
    logger.info(f"Max connections : {settings.MAX_CONNECTIONS_PER_DAY}/day")
    logger.info(f"Max DMs         : {settings.MAX_DMS_PER_DAY}/day")
    logger.info(f"Output CSV      : {settings.OUTPUT_CSV}")
    logger.info(f"Login           : {'YES — ' + settings.ACCOUNTS[0]['username'] if settings.ACCOUNTS else 'NO (not configured)'}")
    logger.info(f"Connect         : {'ON' if settings.SEND_CONNECTION_REQUESTS else 'OFF'}")
    logger.info(f"DM              : {'ON' if settings.SEND_DMS else 'OFF'}")
    logger.info(f"Proxy           : {'ON' if settings.USE_PROXY else 'OFF'}")

    Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # Verify undetected-chromedriver
    try:
        import undetected_chromedriver as uc
        logger.info("undetected-chromedriver ready ✓")
    except ImportError:
        logger.error("undetected-chromedriver not installed! Run: pip install undetected-chromedriver")

    # Verify other imports
    try:
        from core.scraper import LinkedInScraper
        from core.linkedin_search import LinkedInSearch
        from core.company_fetcher import CompanyFetcher
        from core.people_finder import PeopleFinder
        from core.messenger import LinkedInMessenger
        logger.info("All modules imported successfully ✓")
    except ImportError as e:
        logger.error(f"Module import failed: {e}")

    logger.info("✓ Dry run passed — ready to scrape!")
    sys.exit(0)


def print_summary(leads: List[dict], elapsed: float):
    print("\n" + "=" * 60)
    print("  LINKEDIN LEAD GENERATION COMPLETE — SUMMARY")
    print("=" * 60)
    print(f"  Total leads found     : {len(leads)}")
    print(f"  Time elapsed          : {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Output                : {settings.OUTPUT_CSV}")
    print("-" * 60)

    # Industry breakdown
    industries: dict = {}
    for lead in leads:
        ind = lead.get("industry", "Other")
        industries[ind] = industries.get(ind, 0) + 1
    if industries:
        print("  By Industry:")
        for ind, n in sorted(industries.items(), key=lambda x: -x[1]):
            bar = "█" * n
            print(f"    {ind:<25} {n:>3}  {bar}")

    # Stats
    with_email = sum(1 for l in leads if l.get("email"))
    with_instagram = sum(1 for l in leads if l.get("instagram"))
    with_person = sum(1 for l in leads if l.get("decision_maker_name"))
    connections_sent = sum(1 for l in leads if l.get("connection_status") == "sent")
    dms_sent = sum(1 for l in leads if l.get("dm_sent"))

    print(f"\n  With email            : {with_email}/{len(leads)}")
    print(f"  With Instagram        : {with_instagram}/{len(leads)}")
    print(f"  With decision maker   : {with_person}/{len(leads)}")
    print(f"  Connections sent      : {connections_sent}")
    print(f"  DMs sent              : {dms_sent}")
    print("=" * 60 + "\n")


def main():
    args = parse_args()
    apply_overrides(args)

    print("\n" + "=" * 60)
    print("  LINKEDIN LEAD GENERATOR")
    print(f"  Influencer Marketing Outreach Tool")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Loaded Accounts: {len(settings.ACCOUNTS)}")
    print("=" * 60)

    if args.dry_run:
        dry_run()

    start = time.time()
    scraper = LinkedInScraper(industries=settings.INDUSTRIES)

    try:
        if args.mode == "followup":
            logger.info("Mode: Follow-up — DM accepted connections")
            dm_count = scraper.run_followup()
            print(f"\n  Follow-up DMs sent: {dm_count}")
            leads = []
        elif args.mode == "search":
            logger.info(f"Mode: Search only ({len(settings.INDUSTRIES)} industries)")
            leads = scraper.run_search_only()
        elif args.mode == "connect":
            logger.info(f"Mode: Connect ({len(settings.INDUSTRIES)} industries)")
            leads = scraper.run()
        else:
            logger.info(f"Mode: FULL ({len(settings.INDUSTRIES)} industries)")
            leads = scraper.run()

    except KeyboardInterrupt:
        logger.warning("\n⚠ Interrupted — data already saved to CSV")
        try:
            reader = CSVExporter(filepath=settings.OUTPUT_CSV)
            leads = reader.get_all_records()
        except Exception:
            leads = []

    elapsed = time.time() - start

    if leads:
        print_summary(leads, elapsed)

    logger.info(f"Total API requests: {scraper.total_requests()}")


if __name__ == "__main__":
    main()
