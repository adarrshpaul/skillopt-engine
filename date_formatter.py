"""Date formatting utilities with type hints."""

from __future__ import annotations

import datetime
from typing import List, Optional, Tuple, Union


class DateFormatter:
    """Formats dates, date ranges, and timestamps into human-readable strings."""

    DEFAULT_DATE_FORMAT: str = "%Y-%m-%d"
    DEFAULT_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%S"
    DEFAULT_DATE_RANGE_FORMAT: str = "%Y-%m-%d to %Y-%m-%d"

    def __init__(
        self,
        date_format: Optional[str] = None,
        timestamp_format: Optional[str] = None,
        date_range_format: Optional[str] = None,
    ) -> None:
        """Initialize the formatter with optional custom format strings.

        Args:
            date_format: Custom format for single dates. Defaults to "%Y-%m-%d".
            timestamp_format: Custom format for timestamps. Defaults to ISO-like format.
            date_range_format: Custom format for date ranges. Defaults to "start to end".
        """
        self.date_format = date_format or self.DEFAULT_DATE_FORMAT
        self.timestamp_format = timestamp_format or self.DEFAULT_TIMESTAMP_FORMAT
        self.date_range_format = date_range_format or self.DEFAULT_DATE_RANGE_FORMAT

    def format_date(self, date: Union[datetime.date, datetime.datetime]) -> str:
        """Format a single date into a string.

        Args:
            date: A date or datetime object to format.

        Returns:
            The formatted date string.