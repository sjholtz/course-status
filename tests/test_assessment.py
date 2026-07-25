import pytest
import logging
from datetime import datetime, timedelta, time
from courseStatus import Assessment, AssessmentMeta


@pytest.fixture(autouse=True)
def reset_assessment_registry():
    """
    Fixture to clear the class-level registry before and after each test.
    This prevents state from leaking between tests.
    """
    Assessment._type_registry.clear()
    yield
    Assessment._type_registry.clear()


def test_assessment_meta_initialization():
    """Test that AssessmentMeta stores times, days, and offsets correctly."""
    due_time = time(17, 0) # 5:00 PM
    due_day = "Friday"
    too_late = timedelta(days=2)
    resubmit = timedelta(days=5)

    # With all offsets
    meta1 = AssessmentMeta(due_time=due_time,
                           due_day=due_day,
                           too_late_offset=too_late,
                           resubmission_offset=resubmit)

    assert meta1.due_time == time(17, 0)
    assert meta1.due_day == "Friday"
    assert meta1.too_late_offset == too_late
    assert meta1.resubmission_offset == resubmit

    # With no offsets (e.g., a strict Final Exam)
    meta2 = AssessmentMeta(due_time=due_time, due_day=due_day)

    assert meta2.too_late_offset is None
    assert meta2.resubmission_offset is None


def test_register_type_meta():
    """Test that meta-information is correctly stored in the class registry."""
    Assessment.register_type_meta("Quiz",
                                  time(17, 0),
                                  "Friday",
                                  timedelta(days=2))
    Assessment.register_type_meta("Assignment",
                                  time(23, 59),
                                  "Wednesday",
                                  timedelta(days=2),
                                  timedelta(days=7))

    assert "Quiz" in Assessment._type_registry
    assert "Assignment" in Assessment._type_registry

    assert Assessment._type_registry["Quiz"].due_day == "Friday"
    assert Assessment._type_registry["Quiz"].resubmission_offset is None
    assert Assessment._type_registry["Assignment"].resubmission_offset == timedelta(days=7)


def test_assessment_initialization_full_offsets():
    """Test standard initialization and deadline calculation with all offsets."""
    # Setup: Sept 2, 2026 is a Wednesday
    due_date = datetime(2026, 9, 2, 23, 59)
    Assessment.register_type_meta(
        "Assignment", time(23, 59), "Wednesday", timedelta(days=2), timedelta(days=5)
    )

    # Execution
    assess = Assessment("Assignment", due_date)

    # Assertion
    assert assess.type == "Assignment"
    assert assess.due_date == due_date
    assert assess.too_late_date == datetime(2026, 9, 4, 23, 59)
    assert assess.resubmission_date == datetime(2026, 9, 7, 23, 59)


def test_assessment_initialization_no_offsets():
    """Test deadline calculation for assessments with no late or resubmission allowed."""
    # Setup: Dec 14, 2026 is a Monday
    due_date = datetime(2026, 12, 14, 12, 0)
    Assessment.register_type_meta("Final", time(12, 0), "Monday")

    # Execution
    assess = Assessment("Final", due_date)

    # Assertion
    assert assess.too_late_date is None
    assert assess.resubmission_date is None


def test_assessment_unregistered_type_raises_error():
    """Test that instantiating an unregistered assessment type raises a ValueError."""
    due_date = datetime(2026, 1, 1, 12, 0)

    with pytest.raises(ValueError) as exc_info:
        Assessment("Lab", due_date)

    assert "Assessment type 'Lab' is missing meta-configuration" in str(exc_info.value)


def test_validate_schedule_strict_time_mismatch():
    """Test that a time mismatch raises a ValueError when strict_validation is True."""
    # Sept 4, 2026 is a Friday. Registered for 5:00 PM (17:00).
    Assessment.register_type_meta("Quiz", time(17, 0), "Friday")

    # Attempting to schedule at 12:00 PM instead
    bad_time_date = datetime(2026, 9, 4, 12, 0)

    with pytest.raises(ValueError, match="scheduled at 12:00:00, but expects 17:00:00"):
        Assessment("Quiz", bad_time_date, strict_validation=True)


def test_validate_schedule_strict_day_mismatch():
    """Test that a day mismatch raises a ValueError when strict_validation is True."""
    # Sept 4, 2026 is a Friday. Registered for Wednesday.
    Assessment.register_type_meta("Assignment", time(17, 0), "Wednesday")

    bad_day_date = datetime(2026, 9, 4, 17, 0)

    with pytest.raises(ValueError, match="scheduled on Friday, but expects Wednesday"):
        Assessment("Assignment", bad_day_date, strict_validation=True)


def test_validate_schedule_non_strict_logging(caplog):
    """Test that mismatches only log a debug message when strict_validation is False."""
    # Sept 4, 2026 is a Friday. Registered for Wednesday at 23:59.
    Assessment.register_type_meta("Assignment", time(23, 59), "Wednesday")

    # Completely wrong day and time
    override_date = datetime(2026, 9, 4, 12, 0)

    with caplog.at_level(logging.DEBUG):
        # Should NOT raise an exception
        assess = Assessment("Assignment", override_date, strict_validation=False)

        # Verify the object was created
        assert assess.type == "Assignment"

        # Verify the logger captured both override warnings
        assert "scheduled at 12:00:00, but expects 23:59:00" in caplog.text
        assert "scheduled on Friday, but expects Wednesday" in caplog.text


def test_assessment_repr():
    """Test the string representation of the Assessment object."""
    # Oct 31, 2026 is a Saturday
    due_date = datetime(2026, 10, 31, 23, 59)
    Assessment.register_type_meta("Project", time(23, 59), "Saturday")

    assess = Assessment("Project", due_date)

    expected_repr = "<Assessment(type='Project', due_date=2026-10-31 23:59)>"
    assert repr(assess) == expected_repr
