import pytest
import csv
from pathlib import Path
from courseStatus import AppConfig, Assessment


@pytest.fixture(autouse=True)
def reset_registry():
    """Ensure the Assessment registry is cleared before every test."""
    Assessment._type_registry.clear()


@pytest.fixture
def mock_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provides a mocked config.toml in a mocked XDG_CONFIG_HOME."""
    config_home = tmp_path / ".config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    config_dir = config_home / "courseStatus"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"

    toml_content = """
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
    dates = [
        "5-4",
        "9-1"
    ]
    final_dates = [
        "9-4",
        "9-8"
    ]
    exclude_dates = [
        "5-19",
        "7-9",
        "7-10",
        "7-11",
        "7-12",
        "7-13"
    ]

    [Course.Assessments]
    non_academic = [
        "Feedback Survey",
        "Introductory Quiz"
    ]
    late_header_suffix = "Late"

    [Course.Assessments.Quizzes]
    due_time = "5:00 PM"
    due_day = "Friday"
    too_late_deadline_offset = 14
    due_in_modules = ["1-5", "f"]
    final_due_time = "12:00 PM"
    final_due_day = "Monday"

    [Course.Assessments.Quizzes.Adjustments]
    "5-8" = "5-11"

    [Course.Assessments.Assignments]
    due_time = "5:00 PM"
    due_day = "Wednesday"
    too_late_deadline_offset = 14
    resubmission_deadline_offset = 21
    due_in_modules = ["1-2", "5-7", "f"]
    final_due_time = "5:00 PM"
    final_due_day = "Friday"

    [Course.Assessments.Assignments.Adjustments]
    "5-6" = "5-4"

    [Course.Assessments.Geditr]
    due_time = "2:00 AM"
    due_day = "Saturday"
    due_in_modules = ["-f"]
    too_late_deadline_offset = 3
    final_due_time = "4:00 AM"
    final_due_day = "Tuesday"

    [System]
    base_path = "~/Private/grades"
    grades_file_keyword = "Grades"
    missing_file_keyword = "missingAssignments"
    output_file_prefix = "status-"

    # CSV Header Mappings
    grades_student_col = "Student"
    grades_email_col = "SIS Login ID"
    missing_student_col = "Student Name"
    missing_assignment_col = "Assignment Name"

    assignment_code_delimiter = " "
    assignment_code_index = 1

    [Mail_Merge]
    domain = "d.university.edu"
    headers = [
        "Course",
        "First Name",
        "Last Name",
        "Email",
        "As Of Date",
        "Midterm Alert",
        "Modules Behind",
        "Last Module",
        "Current Module",
        "No Work Done",
        "Nothing Late"
    ]
    assessment_too_late_header_suffix = "Late"
    assessment_too_late_date_header_suffix = "Late Date"
    assessment_resubmit_header_suffix = "Resubmit"
    assessment_resubmit_date_header_suffix = "Resubmit Date"

    date_format = "%-I:%M %p on %A %-d %B %Y"
    """

    config_path.write_text(toml_content, encoding="utf-8")
    return config_path


@pytest.fixture
def app_config(mock_config_file: Path) -> AppConfig:
    return AppConfig("CS", "1151")


@pytest.fixture
def mock_missing_csv_file(tmp_path: Path) -> Path:
    """Provides a mocked missing assignments export using dates accurately reflecting the term (May-Sep)."""
    csv_path = tmp_path / "missingAssignments-06-15-2026.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["Student Name", "ID", "SIS", "Course", "Sec", "Assignment Name", "Due"]
        )
        writer.writerow(
            [
                "Doe, John",
                "123",
                "",
                "CS1151",
                "001",
                "CS1151 A2: Module 2 Assignment",
                "2026-05-13",
            ]
        )
        writer.writerow(
            [
                "Doe, John",
                "123",
                "",
                "CS1151",
                "001",
                "CS1151 G3a: Module 3 Geditr",
                "2026-05-23",
            ]
        )
        writer.writerow(
            [
                "Smith, Jane",
                "124",
                "",
                "CS1151",
                "006",
                "CS1151 Q3d: Module 3 Quiz 4",
                "2026-05-22",
            ]
        )
    return csv_path
