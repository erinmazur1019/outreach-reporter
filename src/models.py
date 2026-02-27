"""
Data models used across the pipeline.
"""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class ChannelCounts:
    """Raw engagement counts per channel before categorisation."""
    whatsapp: int = 0
    smartlead_email: int = 0
    linkedin: int = 0   # manual or LinkedIn Sales Navigator
    telegram: int = 0   # manual via Slack slash command
    signal: int = 0     # manual via Slack slash command


@dataclass
class CategoryCounts:
    """Contacts broken out by their lead-type property."""
    creators: int = 0
    agencies: int = 0
    affiliates: int = 0
    unknown: int = 0    # contacts without a recognised lead_type


@dataclass
class DailyReport:
    report_date: date = field(default_factory=date.today)
    channels: ChannelCounts = field(default_factory=ChannelCounts)
    categories: CategoryCounts = field(default_factory=CategoryCounts)

    # All unique HubSpot contact IDs touched across every channel
    unique_contact_ids: set[str] = field(default_factory=set)

    @property
    def total_creators(self) -> int:
        """Unique creator contacts reached across all channels."""
        return self.categories.creators

    @property
    def total_outreach(self) -> int:
        return len(self.unique_contact_ids)

    def sheets_row(self) -> list:
        """Return the row to append to Google Sheets (columns A-D only).

        Sheet layout:
          A: Date
          B: Creators Contacted
          C: Agencies Contacted
          D: Affiliates/Partners Contacted
          E-G: Contracts Sent / Contracts Signed / Everflow Sign Ups — filled manually, not by this script
        """
        return [
            str(self.report_date),
            self.total_creators,
            self.categories.agencies,
            self.categories.affiliates,
        ]

    def slack_summary(self) -> str:
        """Return a formatted Slack message."""
        lines = [
            f"*📊 Daily Outreach Report — {self.report_date}*",
            "",
            f"👀  *Total unique contacts reached:* {self.total_outreach}",
            "",
            "*By channel:*",
            f"  • WhatsApp:      `{self.channels.whatsapp}`",
            f"  • Email (SmartLead replies): `{self.channels.smartlead_email}`",
            f"  • LinkedIn:      `{self.channels.linkedin}`",
            f"  • Telegram:      `{self.channels.telegram}`",
            f"  • Signal:        `{self.channels.signal}`",
            "",
            "*By lead type:*",
            f"  • Creators:      `{self.categories.creators}`",
            f"  • Agencies:      `{self.categories.agencies}`",
            f"  • Affiliates:    `{self.categories.affiliates}`",
        ]
        if self.categories.unknown:
            lines.append(
                f"  • Uncategorised: `{self.categories.unknown}` "
                f"_(set the `lead_type` property in HubSpot to fix)_"
            )
        lines += ["", "Great work everyone! 💪"]
        return "\n".join(lines)
