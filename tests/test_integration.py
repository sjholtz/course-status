import sys
import csv
import pytest
from pathlib import Path
from datetime import datetime as real_datetime
from typing import Any
from unittest.mock import patch
from courseStatus import main, AppConfig, Cohort


def test_integration_dynamic_assessments(
    app_config: AppConfig, tmp_path: Path, mock_missing_csv_file: Path
) -> None:
    """End-to-end integration test verifying that dynamic outputs are correctly appended."""

    # 1. Prepare mock grades CSV
    grades_csv_path: Path = tmp_path / "Grades 06-15-2026.csv"
    with open(grades_csv_path, "w", newline="") as f:
        writer: Any = csv.writer(f)
        writer.writerow(["Student", "ID", "Section", "SIS Login ID"])
        writer.writerow(["Points Possible", "", "", ""])
        writer.writerow(["Student, Test", "", "", ""])
        # Remaining rows: Standard parsed data
        writer.writerow(["Doe, John", "123", "001", "jdoe@university.edu"])

    # 2. Initialize cohort and load data
    cohort = Cohort(app_config, 7, "06/15/2026", 0, 2026)
    cohort.load_grades(grades_csv_path)
    cohort.load_missing_work(mock_missing_csv_file)

    # 3. Generate report
    out_path = tmp_path / "status-2026-06-15.csv"

    # Simulating generation on Aug 1, 2026 to ensure the offsets trigger
    cohort.generate_report(out_path, real_datetime(2026, 8, 1))

    # 4. Verify output results
    assert out_path.exists()

    with open(out_path, "r") as f:
        reader = csv.reader(f)
        rows = list(reader)

        headers = rows[0]
        data_row = rows[1]

        # Verify header length aligns with the dynamically expanded headers
        assert len(headers) == len(app_config.headers)
        assert len(data_row) == len(headers)

        # Verify dynamic "Late Date" and "Resubmit Date" headers are properly appended
        assert "Quizzes Late Date" in headers
        assert "Assignments Resubmit Date" in headers
        assert "Geditr Late Date" in headers

        # Verify standard email domain replacement behavior matches the AppConfig
        assert "jdoe@d.university.edu" in data_row


# Create a fake datetime class that returns our target date for now()
# but acts normally for everything else (like instantiating dates or strptime).
class MockDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return real_datetime(2026, 6, 15)


def test_main_ignores_past_year_files(
    app_config: AppConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that the CLI correctly identifies the current year's files and ignores past years."""

    # 1. Set up the mocked course directory structure
    course_dir = tmp_path / "cs1151"
    course_dir.mkdir(parents=True)

    # Override the base_path_obj in the initialized config to point to our tmp_path
    app_config.base_path_obj = tmp_path

    # 2. Create dummy files for both the current year (2026) and a past year (2025)
    files_to_create = [
        "Grades 06-15-2025.csv",
        "Grades 06-15-2026.csv",
        "missingAssignments 06-15-2025.csv",
        "missingAssignments 06-15-2026.csv",
    ]

    for filename in files_to_create:
        file_path = course_dir / filename
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            # Write standard dummy headers so the csv reader doesn't crash
            if "Grades" in filename:
                writer.writerows(
                    [
                        ["Student", "SIS Login ID"],
                        ["Points Possible", ""],
                        ["Student, Test", ""],
                    ]
                )
            else:
                writer.writerow(["Student Name", "Assignment Name"])

    # 3. Mock CLI arguments and datetime to simulate running the tool on 06/15/2026
    test_args = ["courseStatus.py", "-c", "CS", "1151", "-m", "7", "-d", "06-15"]
    monkeypatch.setattr(sys, "argv", test_args)

    # 4. Patch AppConfig and datetime
    with patch("courseStatus.AppConfig", return_value=app_config), patch(
        "courseStatus.datetime", MockDatetime
    ):

        # Run main() and ensure it doesn't sys.exit(1) due to file discovery failure
        try:
            main()
        except SystemExit as e:
            pytest.fail(f"main() exited unexpectedly with code {e}")

    # 5. Verify the tool only generated a report for the 2026 target year
    out_path = course_dir / "status-2026-06-15.csv"
    wrong_out_path = course_dir / "status-2025-06-15.csv"

    assert (
        out_path.exists()
    ), "The report for the current year (2026) was not generated."
    assert (
        not wrong_out_path.exists()
    ), "A report was incorrectly generated for a past year."
