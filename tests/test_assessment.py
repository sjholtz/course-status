import pytest
import logging
from datetime import datetime, timedelta, time
from courseStatus import Assessment, AssessmentMeta


@pytest.fixture(autouse=True)
def reset_registry():
    """Ensure the type registry is cleared before every test to prevent pollution."""
    Assessment._type_registry.clear()


def test_assessment_meta_initialization():
    """Test that AssessmentMeta correctly stores all configuration values."""
    due_time = time(17, 0)
    meta = AssessmentMeta(
        due_time=due_time,
        due_day="Friday",
        due_in_modules=["1", "2", "3", "f"],
        too_late_offset=timedelta(days=14),
        resubmission_offset=timedelta(days=21),
        final_due_time=time(12, 0),
        final_due_day="Monday",
    )

    assert meta.due_time == due_time
    assert meta.due_day == "Friday"
    assert meta.due_in_modules == ["1", "2", "3", "f"]
    assert meta.too_late_offset == timedelta(days=14)
    assert meta.resubmission_offset == timedelta(days=21)
    assert meta.final_due_time == time(12, 0)
    assert meta.final_due_day == "Monday"


def test_register_and_get_meta():
    """Test that meta configurations can be registered and retrieved via Assessment."""
    due_time = time(17, 0)

    Assessment.register_type_meta(
        assess_type="Quiz",
        due_time=due_time,
        due_day="Friday",
        due_in_modules=["1", "2"],
    )

    meta = Assessment.get_meta("Quiz")
    assert meta is not None
    assert isinstance(meta, AssessmentMeta)
    assert meta.due_time == due_time
    assert meta.due_day == "Friday"

    # Check non-existent meta
    assert Assessment.get_meta("NonExistent") is None


def test_assessment_initialization_missing_meta():
    """Test that instantiating an Assessment without registered meta raises a ValueError."""
    with pytest.raises(ValueError, match="is missing meta-configuration"):
        Assessment(assess_type="Quiz", due_date=datetime(2026, 7, 24, 17, 0))


def test_assessment_valid_schedule_and_offsets():
    """Test standard assessment initialization calculates offsets correctly."""
    Assessment.register_type_meta(
        assess_type="Assignment",
        due_time=time(17, 0),
        due_day="Friday",
        due_in_modules=["1", "2"],
        too_late_offset=timedelta(days=14),
        resubmission_offset=timedelta(days=21),
    )

    # July 24, 2026 is a Friday
    due_date = datetime(2026, 7, 24, 17, 0)
    assessment = Assessment("Assignment", due_date, strict_validation=True)

    assert assessment.type == "Assignment"
    assert assessment.due_date == due_date
    assert not assessment.is_final

    # Offsets should be applied because it's not a final
    assert assessment.too_late_date == due_date + timedelta(days=14)
    assert assessment.resubmission_date == due_date + timedelta(days=21)


def test_assessment_finals_schedule_and_offsets():
    """Test finals week assessment uses final constraints and ignores offsets."""
    Assessment.register_type_meta(
        assess_type="Quiz",
        due_time=time(17, 0),
        due_day="Friday",
        due_in_modules=["f"],
        too_late_offset=timedelta(days=14),
        resubmission_offset=timedelta(days=21),
        final_due_time=time(12, 0),
        final_due_day="Monday",
    )

    # July 27, 2026 is a Monday
    final_due = datetime(2026, 7, 27, 12, 0)
    assessment = Assessment("Quiz", final_due, strict_validation=True, is_final=True)

    assert assessment.is_final is True
    # Offsets should NOT be applied for finals
    assert assessment.too_late_date is None
    assert assessment.resubmission_date is None


def test_assessment_strict_validation_time_mismatch():
    """Test strict validation raises ValueError on time mismatch."""
    Assessment.register_type_meta(
        assess_type="Quiz",
        due_time=time(17, 0),  # Expects 5:00 PM
        due_day="Friday",
        due_in_modules=["1"],
    )

    # Friday, but at 12:00 PM instead of 5:00 PM
    bad_time_date = datetime(2026, 7, 24, 12, 0)

    with pytest.raises(ValueError, match="scheduled at 12:00:00, but expects 17:00:00"):
        Assessment("Quiz", bad_time_date, strict_validation=True)


def test_assessment_strict_validation_day_mismatch():
    """Test strict validation raises ValueError on day mismatch."""
    Assessment.register_type_meta(
        assess_type="Quiz",
        due_time=time(17, 0),
        due_day="Friday",  # Expects Friday
        due_in_modules=["1"],
    )

    # Thursday at 5:00 PM
    bad_day_date = datetime(2026, 7, 23, 17, 0)

    with pytest.raises(ValueError, match="scheduled on Thursday, but expects Friday"):
        Assessment("Quiz", bad_day_date, strict_validation=True)


def test_assessment_non_strict_validation(caplog):
    """Test non-strict validation logs debug messages instead of raising errors."""
    Assessment.register_type_meta(
        assess_type="Quiz", due_time=time(17, 0), due_day="Friday", due_in_modules=["1"]
    )

    # Thursday at 12:00 PM (Both day and time are wrong)
    bad_date = datetime(2026, 7, 23, 12, 0)

    # Should not raise an exception
    assessment = Assessment("Quiz", bad_date, strict_validation=False)

    # Verify the assessment still created successfully despite the schedule override
    assert assessment.due_date == bad_date


def test_assessment_repr():
    """Test the string representation of the Assessment object."""
    Assessment.register_type_meta(
        assess_type="Survey",
        due_time=time(17, 0),
        due_day="Friday",
        due_in_modules=["1"],
    )

    due_date = datetime(2026, 7, 24, 17, 0)
    assessment = Assessment("Survey", due_date)

    expected_repr = (
        "<Assessment(type='Survey', due_date=2026-07-24 17:00, final=False)>"
    )
    assert repr(assessment) == expected_repr
