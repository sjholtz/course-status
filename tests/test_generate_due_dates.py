import pytest
from datetime import datetime, timedelta
from dateutil.rrule import WE, FR
import courseStatus


def test_generate_due_dates(monkeypatch):
    """Test the generation of quiz and assignment due dates."""

    # 1. Setup mock configuration data
    # Let's assume a short 4-week course starting Monday, May 11, 2026
    mock_start = datetime(2026, 5, 11)
    # Ending on June 8, 2026
    mock_end = datetime(2026, 6, 8)
    # Assessments due at 5:00 PM
    mock_due_time = timedelta(hours=17)

    # Let's exclude the second Friday (May 22, 2026) to test the
    # exclude date logic
    mock_exclude = datetime(2026, 5, 22)

    # 2. Monkeypatch the global variables in courseStatus
    monkeypatch.setattr(courseStatus, "COURSE_DATES", [mock_start, mock_end])
    monkeypatch.setattr(courseStatus, "DUE_TIME", mock_due_time)
    monkeypatch.setattr(courseStatus, "QUIZ_DUE_DAY_OF_WEEK", FR)
    monkeypatch.setattr(courseStatus, "ASSIGNMENT_DUE_DAY_OF_WEEK", WE)
    monkeypatch.setattr(courseStatus, "TOO_LATE_OFFSET", timedelta(weeks=1))
    monkeypatch.setattr(courseStatus, "EXCLUDE_DATES", [mock_exclude])

    # 3. Call the function
    quizzes, assignments = courseStatus.generate_due_dates()

    # 4. Assert expected outcomes for quizzes
    # Quizzes happen on Fridays.
    # Start: Monday, May 11 -> First Friday is May 15.
    # Exclude date: May 22 is excluded.
    # Next Friday: May 29.
    # Until: mock_end (June 8) - 1 week offset = June 1.
    # So we only expect May 15 and May 29.

    assert len(quizzes) == 2, "Should generate exactly 2 quiz dates"
    assert quizzes[0] == datetime(2026, 5, 15, 17, 0)
    assert quizzes[1] == datetime(2026, 5, 29, 17, 0)

    # 5. Assert expected outcomes for assignments
    # Assignments happen on Wednesdays, starting 1 week after the
    #    course start.
    # Start offset: Monday, May 11 + 1 week = May 18 -> First
    #    Wednesday is May 20.
    # Next Wednesday: May 27.
    # Until: mock_end (June 8) - 1 week = June 1.
    # Plus the final: mock_end (June 8) + 1 week = June 15.

    assert len(assignments) == 3, "Should generate exactly 3 assignment dates"
    assert assignments[0] == datetime(2026, 5, 20, 17, 0)
    assert assignments[1] == datetime(2026, 5, 27, 17, 0)
    assert assignments[2] == datetime(2026, 6, 15, 17, 0)
