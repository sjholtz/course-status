from courseStatus import Student, AppConfig
from typing import Dict, Union


def test_student_get_status(app_config: AppConfig) -> None:
    """Tests the get_status logic for calculating modules behind and missing work."""
    student: Student = Student("Doe, John", "jdoe@university.edu", app_config)
    student.add_missing_assignment("Assignment Q1a")
    student.add_missing_assignment("Feedback Survey")  # Should be ignored

    status: Dict[str, Union[str, int]] = student.get_status(current_module=3)

    assert status["modules_behind"] == 2  # Current 3 & Last module worked on 1
    assert status["no_work_done"] == 1
    assert status["nothing_late"] == 0
    assert status["last_module"] == 1
