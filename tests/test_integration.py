import csv
from pathlib import Path
from datetime import datetime
from typing import Any
from courseStatus import AppConfig, Cohort


def test_integration_dynamic_assessments(
    app_config: AppConfig, tmp_path: Path, mock_missing_csv_file: Path
) -> None:
    """End-to-end integration test verifying that dynamic outputs are correctly appended."""
    grades_csv_path: Path = tmp_path / "Grades 06-15-2026.csv"
    with open(grades_csv_path, "w", newline="") as f:
        writer: Any = csv.writer(f)
        writer.writerow(["Student", "ID", "Section", "SIS Login ID"])
        writer.writerow(["Points Possible", "", "", ""])
        writer.writerow(["Student, Test", "", "", ""])
        # Remaining Rows: Standard parsed data
        writer.writerow(["Doe, John", "123", "001", "jdoe@university.edu"])

    cohort = Cohort(app_config, 1151, 7, "06/15/2026", 0, 2026)
    cohort.load_grades(grades_csv_path)
    cohort.load_missing_work(mock_missing_csv_file)

    out_path = tmp_path / "status-2026-06-15.csv"

    cohort.generate_report(out_path, datetime(2026, 8, 1))

    assert out_path.exists()

    with open(out_path, "r") as f:
        reader = csv.reader(f)
        rows = list(reader)

        headers = rows[0]
        data_row = rows[1]

        assert len(headers) == len(app_config.headers)
        assert len(data_row) == len(headers)

        assert "Quizzes Late Date" in headers
        assert "Geditr Late Date" in headers

        assert "jdoe@d.university.edu" in data_row
