"""
Google Sheets client — appends one row per day to the BizDev worksheet.

Authentication: Service Account JSON key.
Library: gspread + google-auth
Docs: https://docs.gspread.org/en/latest/oauth2.html#for-bots-using-service-account
"""

import logging
from datetime import date

import gspread
from google.oauth2.service_account import Credentials

from src.config import cfg
from src.models import DailyReport

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Expected column headers in row 1 of the BizDev sheet.
# The order MUST match DailyReport.sheets_row().
EXPECTED_HEADERS = [
    "Date",
    "Creators Contacted",
    "Agencies Contacted",
    "Affiliates/Partners Contacted",
]


def _get_worksheet() -> gspread.Worksheet:
    creds = Credentials.from_service_account_file(
        cfg.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(cfg.GOOGLE_SPREADSHEET_ID)
    return spreadsheet.worksheet(cfg.GOOGLE_WORKSHEET_NAME)


def _ensure_headers(ws: gspread.Worksheet) -> None:
    """Write headers to row 1 if the sheet is empty."""
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(EXPECTED_HEADERS, value_input_option="RAW")
        logger.info("Wrote headers to empty sheet.")


def append_daily_row(report: DailyReport) -> None:
    """
    Append one row for today's report.
    If a row for today already exists, it is updated in place instead.
    """
    ws = _get_worksheet()
    _ensure_headers(ws)

    today_str = str(report.report_date)
    row_data = report.sheets_row()

    # Check if a row for today already exists (column A)
    date_col = ws.col_values(1)
    if today_str in date_col:
        row_index = date_col.index(today_str) + 1  # 1-based
        ws.update(
            f"A{row_index}:{chr(ord('A') + len(row_data) - 1)}{row_index}",
            [row_data],
            value_input_option="RAW",
        )
        logger.info("Updated existing row %d for %s", row_index, today_str)
    else:
        ws.append_row(row_data, value_input_option="RAW")
        logger.info("Appended new row for %s", today_str)
