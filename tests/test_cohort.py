import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, Union, Any
from courseStatus import AppConfig, Cohort


def test_cohort_initialization_and_student_creation(app_config: AppConfig):
    """Test Cohort creates a Course and manages a dictionary of Students."""
    cohort = Cohort(
        config=app_config,
        course_num=1151,
        current_module=7,
        as_of_date_str="06/15/2026",
        midterm_alert=0,
        term_year=2026,
    )

    assert cohort.course is not None
    student = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    student_again = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    assert student is student_again
    assert len(cohort._students) == 1


def test_cohort_load_grades(app_config: AppConfig, tmp_path: Path) -> None:
    """Tests the load_grades method for parsing the main canvas export."""
    csv_path: Path = tmp_path / "Grades.csv"

    f: Any
    with open(csv_path, "w", newline="") as f:
        writer: Any = csv.writer(f)
        writer.writerow(["Student", "ID", "Section", "SIS Login ID"])
        writer.writerow(["Points Possible", "", "", ""])
        writer.writerow(["Student, Test", "", "", ""])
        # Remaining Rows: Standard parsed data
        writer.writerow(["Doe, John", "123", "001", "jdoe@university.edu"])
        writer.writerow(
            ["Student, Test", "125", "001", "test@university.edu"]
        )  # Should be skipped in processing

    cohort: Cohort = Cohort(app_config, 1151, 3, "06/15/2026", 1, 2026)
    cohort.load_grades(csv_path)

    assert len(list(cohort)) == 1
    assert "Doe, John" in cohort._students
    assert "Student, Test" not in cohort._students


def test_cohort_load_missing_work(app_config: AppConfig, mock_missing_csv_file: Path):
    """Test that CSV missing assignment data is correctly parsed and bound to Students."""
    cohort = Cohort(app_config, 1151, 5, "06/15/2026", 0, 2026)

    # Create the students that exist in the mock CSV
    cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    cohort.get_or_create_student("Smith, Jane", "jsmith@example.com")

    # Process the CSV
    cohort.load_missing_work(mock_missing_csv_file)

    # Validate John Doe
    john = cohort.get_or_create_student("Doe, John", "jdoe@example.com")
    assert len(john.missing_assignments) == 2
    assert "CS1151 A2: Module 2 Assignment" in john.missing_assignments
    assert "CS1151 G3a: Module 3 Geditr" in john.missing_assignments

    # Validate Jane Smith
    jane = cohort.get_or_create_student("Smith, Jane", "jsmith@example.com")
    assert len(jane.missing_assignments) == 1
    assert "CS1151 Q3d: Module 3 Quiz 4" in jane.missing_assignments


def test_cohort_calculate_dynamic_deadlines(app_config: AppConfig) -> None:
    """Tests that dynamic deadlines are calculated and added to the tracking dictionary."""
    cohort = Cohort(app_config, 1151, 3, "06-15-2026", 1, 2026)

    today: datetime = datetime(2026, 7, 1)
    deadlines: Dict[str, Union[int, str]] = cohort._calculate_deadlines(today)

    assert "Quizzes_late" in deadlines
    assert "Assignments_late" in deadlines
    assert "Assignments_resubmit" in deadlines
    assert "Geditr_late" in deadlines

    assert int(deadlines["Geditr_late"]) > 0
    assert deadlines["Geditr_late_date"] != -1


def test_ignored_students_are_skipped(app_config: AppConfig, tmp_path: Path) -> None:
    """Tests that ignored students are successfully bypassed during CSV load."""
    csv_path: Path = tmp_path / "Grades_With_Ignored.csv"

    with open(csv_path, "w", newline="") as f:
        writer: Any = csv.writer(f)
        writer.writerow(["Student", "ID", "Section", "SIS Login ID"])
        writer.writerow(["Points Possible", "", "", ""])
        writer.writerow(["Student, Test", "", "", ""])
        # Remaining Rows: Standard parsed data
        writer.writerow(["Doe, John", "123", "001", "jdoe@university.edu"])
        writer.writerow(["Points Possible", "124", "001", "points@university.edu"])
        writer.writerow(["Student, Test", "125", "001", "test1@university.edu"])

    cohort = Cohort(app_config, 1151, 7, "06-15-2026", 1, 2026)
    cohort.load_grades(csv_path)

    assert "Doe, John" in cohort._students
    assert "Points Possible" not in cohort._students
    assert "Student, Test" not in cohort._students
