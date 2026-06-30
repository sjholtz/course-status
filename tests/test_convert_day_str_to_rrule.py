import pytest
from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU
import courseStatus


def test_convert_day_str_to_rrule_full_name():
    """Test that full day names map to the correct rrule weekday."""
    assert courseStatus.convert_day_str_to_rrule("Monday") == MO
    assert courseStatus.convert_day_str_to_rrule("Wednesday") == WE
    assert courseStatus.convert_day_str_to_rrule("Friday") == FR
    assert courseStatus.convert_day_str_to_rrule("Sunday") == SU


def test_convert_day_str_to_rrule_unambiguous_prefix():
    """Test that single-letter unambiguous prefixes map correctly."""
    assert courseStatus.convert_day_str_to_rrule("M") == MO
    assert courseStatus.convert_day_str_to_rrule("W") == WE
    assert courseStatus.convert_day_str_to_rrule("F") == FR


def test_convert_day_str_to_rrule_case_insensitive():
    """Test that the matching is case-insensitive."""
    assert courseStatus.convert_day_str_to_rrule("mOn") == MO
    assert courseStatus.convert_day_str_to_rrule("friDAY") == FR
    assert courseStatus.convert_day_str_to_rrule("wEd") == WE


def test_convert_day_str_to_rrule_disambiguated_prefix():
    """Test that multi-letter prefixes correctly resolve 'T' and 'S' days."""
    assert courseStatus.convert_day_str_to_rrule("Tu") == TU
    assert courseStatus.convert_day_str_to_rrule("Th") == TH
    assert courseStatus.convert_day_str_to_rrule("Sa") == SA
    assert courseStatus.convert_day_str_to_rrule("Su") == SU


def test_convert_day_str_to_rrule_ambiguous_prefix():
    """Test that ambiguous prefixes (like 'T' or 'S') raise a ValueError."""
    with pytest.raises(ValueError, match="Illegal or insufficient due day"):
        courseStatus.convert_day_str_to_rrule("T")

    with pytest.raises(ValueError, match="Illegal or insufficient due day"):
        courseStatus.convert_day_str_to_rrule("S")


def test_convert_day_str_to_rrule_invalid_string():
    """Test that completely invalid day strings raise a ValueError."""
    with pytest.raises(ValueError, match="Illegal or insufficient due day"):
        courseStatus.convert_day_str_to_rrule("Funday")

    with pytest.raises(ValueError, match="Illegal or insufficient due day"):
        courseStatus.convert_day_str_to_rrule("XYZ")
