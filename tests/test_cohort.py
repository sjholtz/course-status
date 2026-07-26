import pytest
from pathlib import Path
from courseStatus import Cohort, AppConfig, Student


def test_cohort_initialization_and_student_creation(app_config: AppConfig):
    """Test Cohort creates a Course and manages a dictionary of Students."""
    cohort = Cohort(
        config=app_config,
        course_num=1151,
        current_module=5,
        as_of_date_str="2/5/2026",
        midterm_alert=0,
        term_year=2026,
    )

    # 1. Verify internal Course was instantiated
    assert cohort.course is not None

    # 2. Add and retrieve a student
    student = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    assert isinstance(student, Student)

    # 3. Verify retrieving the exact same student string returns the same object
    student_again = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    assert student is student_again


def test_cohort_load_missing_work(app_config: AppConfig, mock_missing_csv_file: Path):
    """Test that CSV missing assignment data is correctly parsed and bound to Students."""
    cohort = Cohort(app_config, 1151, 5, "2/5/2026", 0, 2026)

    # Create the students that exist in the mock CSV
    cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    cohort.get_or_create_student("Smith, Jane", "jsmith@example.com")

    # Process the CSV
    cohort.load_missing_work(mock_missing_csv_file)

    # Validate John Doe
    john = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    assert len(john.missing_assignments) == 2
    assert "CS1151 A2: Module 2 Assignment" in john.missing_assignments

    # Validate Jane Smith
    jane = cohort.get_or_create_student("Smith, Jane", "jsmith@example.com")
    assert len(jane.missing_assignments) == 1
    assert "CS1151 Q3d: Module 3 Quiz 4" in jane.missing_assignments


# from courseStatus import Cohort, AppConfig

# def test_cohort_init(app_config: AppConfig) -> None:
#     """Tests the initialization of the Cohort class."""
#     cohort: Cohort = Cohort(app_config, 1151, 3, "02-15-2026", 1, 2026)

#     assert cohort.course_num == 1151
#     assert cohort.current_module == 3
#     assert cohort.as_of_date_str == "02-15-2026"
#     assert cohort.midterm_alert == 1
#     assert len(cohort.modules) > 0
