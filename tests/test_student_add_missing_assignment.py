from courseStatus import Student, AppConfig

def test_student_add_missing_assignment(app_config: AppConfig) -> None:
    """Tests the add_missing_assignment method."""
    student: Student = Student("Doe, John",
                               "jdoe@university.edu",
                               app_config)
    student.add_missing_assignment("Assignment Q1a")

    assert len(student.missing_assignments) == 1
    assert student.missing_assignments[0] == "Assignment Q1a"
