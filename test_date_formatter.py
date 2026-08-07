import unittest
from datetime import date, datetime, time
from date_formatter import DateFormatter


class TestDateFormatter(unittest.TestCase):
    """Unit tests for the DateFormatter class."""

    def setUp(self):
        self.formatter = DateFormatter()

    def test_format_date_basic(self):
        """Test basic date formatting."""
        result = self.formatter.format_date(date(2024, 1, 15))
        self.assertEqual(result, "2024-01-15")

    def test_format_date_with_time(self):
        """Test formatting date with time."""
        result = self.formatter.format_date(datetime(2024, 1, 15, 14, 30))
        self.assertEqual(result, "2024-01-15 14:30:00")

    def test_format_date_custom_format(self):
        """Test custom date format."""
        result = self.formatter.format_date(date(2024, 1, 15), "%B %d, %Y")
        self