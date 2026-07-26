import csv
from courseStatus import Cohort, AppConfig
from pathlib import Path
from typing import Any


def test_cohort_load_grades(app_config: AppConfig, tmp_path: Path) -> None:
    """Tests the load_grades method for parsing the main canvas export."""
    csv_path: Path = tmp_path / "Grades.csv"

    f: Any
    with open(csv_path, "w", newline="") as f:
        writer: Any = csv.writer(f)
        writer.writerow(["Header 1"])
        writer.writerow(["Header 2"])
        writer.writerow(["Doe, John", "ID", "Sec", "jdoe@university.edu"])
        writer.writerow(
            ["Student, Test", "ID", "Sec", "test@university.edu"]
        )  # Should be skipped in processing

    cohort: Cohort = Cohort(app_config, 1151, 3, "02-15-2026", 1, 2026)
    cohort.load_grades(csv_path)

    assert len(list(cohort)) == 1
    assert "Doe, John" in cohort._students
    assert "Student, Test" not in cohort._students
