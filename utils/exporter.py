"""
CSV Exporter — LinkedIn Leads
==============================
Saves lead data to CSV with:
- Auto-deduplication (no duplicate companies/people)
- Append mode (safe to re-run)
- Timestamped backups
- Clean field ordering
"""

import csv
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from utils.logger import get_logger
import config.settings as g_settings

logger = get_logger()

# Output CSV columns for LinkedIn leads
CSV_COLUMNS = [
    "company_name",
    "industry",
    "company_linkedin_url",
    "website",
    "company_size",
    "location",
    "email",
    "instagram",
    "decision_maker_name",
    "decision_maker_title",
    "decision_maker_linkedin",
    "connection_status",
    "dm_sent",
    "dm_message",
    "source_keyword",
    "scraped_at",
]


class CSVExporter:
    """
    Handles all CSV write operations.

    Features:
    - Creates file + header if not exists
    - Appends new rows; skips duplicates (by company_linkedin_url)
    - Creates backup before each write session
    - Returns export statistics
    """

    def __init__(self, filepath: str = None):
        self.filepath = filepath or g_settings.OUTPUT_CSV
        self._existing_keys: set = set()
        self._backed_up_this_session: bool = False
        Path(g_settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        self._load_existing_keys()

    # ── Public API ────────────────────────────────────────────────────────────

    def export(self, leads: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Write leads to CSV.
        Returns stats: {total, new, skipped, duplicates}
        """
        if not leads:
            logger.warning("No leads to export")
            return {"total": 0, "new": 0, "skipped": 0, "duplicates": 0}

        self._backup_if_exists()

        new_rows = []
        duplicates = 0
        skipped = 0

        for lead in leads:
            # Deduplicate by company URL + decision maker LinkedIn URL
            dedup_key = (
                lead.get("company_linkedin_url", "")
                + "|"
                + lead.get("decision_maker_linkedin", "")
            )
            if not lead.get("company_name"):
                skipped += 1
                continue
            if dedup_key in self._existing_keys:
                duplicates += 1
                logger.debug(f"Duplicate skipped: {lead.get('company_name')}")
                continue

            row = self._build_row(lead)
            new_rows.append(row)
            self._existing_keys.add(dedup_key)

        self._write_rows(new_rows)

        stats = {
            "total": len(leads),
            "new": len(new_rows),
            "skipped": skipped,
            "duplicates": duplicates,
        }

        logger.info(
            f"CSV Export → {self.filepath} | "
            f"New: {stats['new']} | Duplicates skipped: {stats['duplicates']}"
        )
        return stats

    def get_all_records(self) -> List[Dict]:
        """Read and return all records currently in the CSV."""
        if not Path(self.filepath).exists():
            return []
        with open(self.filepath, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def total_records(self) -> int:
        return len(self._existing_keys)

    def update_record(self, company_url: str, decision_maker_url: str, updates: Dict):
        """Update specific fields for an existing record (e.g., connection_status, dm_sent)."""
        if not Path(self.filepath).exists():
            return

        records = self.get_all_records()
        updated = False

        for record in records:
            if (record.get("company_linkedin_url") == company_url and
                    record.get("decision_maker_linkedin") == decision_maker_url):
                record.update(updates)
                updated = True
                break

        if updated:
            try:
                with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(records)
                logger.debug(f"Updated record for {company_url}")
            except Exception as e:
                logger.error(f"CSV update failed: {e}")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_existing_keys(self):
        """Load dedup keys already in CSV to prevent duplicates."""
        if not Path(self.filepath).exists():
            return
        try:
            with open(self.filepath, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (
                        row.get("company_linkedin_url", "")
                        + "|"
                        + row.get("decision_maker_linkedin", "")
                    )
                    self._existing_keys.add(key)
            logger.info(f"Loaded {len(self._existing_keys)} existing records from CSV")
        except Exception as e:
            logger.warning(f"Could not read existing CSV: {e}")

    def _write_rows(self, rows: List[Dict]):
        """Append rows to CSV. Creates with header if file doesn't exist."""
        if not rows:
            return

        file_exists = Path(self.filepath).exists()
        mode = "a" if file_exists else "w"

        try:
            with open(self.filepath, mode, newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                    logger.debug(f"Created new CSV: {self.filepath}")
                writer.writerows(rows)
        except Exception as e:
            logger.error(f"CSV write failed: {e}", exc_info=True)
            raise

    def _build_row(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a lead dict into a CSV row."""
        return {
            "company_name":           lead.get("company_name", ""),
            "industry":               lead.get("industry", ""),
            "company_linkedin_url":   lead.get("company_linkedin_url", ""),
            "website":                lead.get("website", ""),
            "company_size":           lead.get("company_size", ""),
            "location":              lead.get("location", ""),
            "email":                  lead.get("email", ""),
            "instagram":              lead.get("instagram", ""),
            "decision_maker_name":    lead.get("decision_maker_name", ""),
            "decision_maker_title":   lead.get("decision_maker_title", ""),
            "decision_maker_linkedin": lead.get("decision_maker_linkedin", ""),
            "connection_status":      lead.get("connection_status", "not_sent"),
            "dm_sent":                lead.get("dm_sent", False),
            "dm_message":             lead.get("dm_message", ""),
            "source_keyword":         lead.get("source_keyword", ""),
            "scraped_at":             lead.get("scraped_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        }

    def _backup_if_exists(self):
        """Create a timestamped backup of the CSV before the first write of this session."""
        if self._backed_up_this_session:
            return
        if not Path(self.filepath).exists():
            return
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.filepath.replace(".csv", f"_backup_{timestamp}.csv")
            shutil.copy2(self.filepath, backup_path)
            logger.debug(f"Backup created: {backup_path}")
            self._backed_up_this_session = True
        except Exception as e:
            logger.warning(f"Backup failed: {e}")
