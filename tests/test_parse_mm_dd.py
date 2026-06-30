import pytest
from datetime import datetime
import courseStatus


def test_parse_mm_dd_valid_date():
    """Test that a standard MM-DD string parses correctly."""
    result = courseStatus.parse_mm_dd("05-14")
    expected = datetime(courseStatus.CURRENT_YEAR, 5, 14)

    assert result == expected


def test_parse_mm_dd_with_whitespace():
    """Test that leading and trailing whitespace is stripped."""
    result = courseStatus.parse_mm_dd("  09-01  ")
    expected = datetime(courseStatus.CURRENT_YEAR, 9, 1)

    assert result == expected


def test_parse_mm_dd_invalid_format(capsys):
    """Test that an invalid string format triggers sys.exit(1)."""
    with pytest.raises(SystemExit) as exception_info:
        courseStatus.parse_mm_dd("invalid-date")

    assert exception_info.value.code == 1

    captured = capsys.readouterr()
    assert "ERROR: In config.ini reading" in captured.err


def test_parse_mm_dd_impossible_date(capsys):
    """Test that a non-existent date (like Feb 30) triggers sys.exit(1)."""
    with pytest.raises(SystemExit) as exception_info:
        courseStatus.parse_mm_dd("02-30")

    assert exception_info.value.code == 1

    captured = capsys.readouterr()
    assert "ERROR: In config.ini reading" in captured.err
