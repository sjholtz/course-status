import pytest
from pathlib import Path
from courseStatus import AppConfig


@pytest.fixture
def mock_config_file(tmp_path: Path) -> Path:
    """Creates a temporary config.toml file for testing."""
    # tmp_path is a built-in pytest fixture that provides a temporary directory
    config_path = tmp_path / "config.toml"

    # Write the TOML data incorporating the new nested Assessments structur
    config_path.write_text(
        """
    [Course]
    prefix = "CS"
    numbers = [1151, 1411]
    first_assess_code = "Q1a"
    number_of_modules = 14
    ignored_students = [
        "Points Possible",
        "Student, Test",
        "Test Student"
    ]
    [Course.Dates]
    dates = ["1-5", "4-24"]
    final_dates = ["4-27", "5-1"]
    exclude_dates = ["1-12", "3-9", "3-10", "3-11", "3-12", "3-13"]

    [Course.Assessments]
    non_academic_assessments = ["Feedback Survey"]

    [Course.Assessments.Quizzes]
    due_time = "5:00 PM"
    due_day = "Friday"
    too_late_deadline_offset = 14
    # Shorthand tests: 1, 2, 3, 5, 6, 13, 14
    due_in_modules = ["-3", "5-6", "13-14"]

    [Course.Assessments.Assignments]
    due_time = "11:59 PM"
    due_day = "Wednesday"
    too_late_deadline_offset = 14
    resubmission_deadline_offset = 21
    # Full span
    due_in_modules = ["1-14"]

    [Course.Assessments.Final]
    due_time = "12:00 PM"
    due_day = "Monday"
    due_in_modules = ["f"]
    final_due_time = "12:00 PM"
    final_due_day = "Monday"

    [System]
    base_path = "~/Private/grades"
    grades_file_keyword = "Grades"
    missing_file_keyword = "missingAssignments"
    output_file_prefix = "status-"
    assignment_code_delimiter = " "
    assignment_code_index = 1

    [Mail_Merge]
    domain = "my.university.edu"
    headers = ["FirstName", "LastName", "Status"]
    date_format = "%Y-%m-%d"
    """,
        encoding="utf-8",
    )

    return config_path


@pytest.fixture
def app_config(mock_config_file: Path) -> AppConfig:
    """Provides an instantiated AppConfig object based on the mocked TOML file."""
    return AppConfig(str(mock_config_file))


@pytest.fixture(
    params=[
        "missingAssignments 2-5-2026.csv",
        "missingAssignments 02-05-2026.csv",
        "missingAssignments-2-5-2026.csv",
        "missingAssignments-02-05-2026.csv",
    ]
)
def mock_missing_csv_file(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """
    Creates a temporary missing assignments CSV file.
    Because it is parametrized, any test using this fixture will
    automatically run multiple times (once for each filename format).
    """
    file_name = request.param
    missing_path = tmp_path / file_name

    # Write some standard mock CSV data
    missing_path.write_text(
        """Student Name,Student ID,Course Name,Course ID,Section Name,Assignment Name,Points Possible, Due Date, Unlock Date
"Doe, John",123,CS1151,999,"001","CS1151 A2: Module 2 Assignment",100,"Feb 4, 2026, 5:00:00 PM CST",
"Doe, John",123,CS1151,999,"001","CS1151: Feedback Survey",0,"Feb 4, 2026, 5:00:00 PM CST",
"Smith, Jane",124,CS1151,999,"006","CS1151 Q3d: Module 3 Quiz 4",12,"Feb 4, 2026, 5:00:00 PM CST",
""",
        encoding="utf-8",
    )

    return missing_path
