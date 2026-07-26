from courseStatus import Student, AppConfig

def test_student_init(app_config: AppConfig) -> None:
    """Tests the initialization and string parsing of the Student class."""
    student: Student = Student("Doe, John",
                               "jdoe@example.com",
                               app_config)

    assert student.first_name == "John"
    assert student.last_name == "Doe"
    assert student.email == "jdoe@my.university.edu"
    assert student.missing_assignments == []

def test_student_get_status_nothing_late(app_config: AppConfig):
    """Test status logic when the student has no missing assignments."""
    student = Student("Doe, John", "jdoe@example.com", app_config)

    status = student.get_status(current_module=3)
    assert status["nothing_late"] == 1
    assert status["no_work_done"] == 0
    assert status["last_module"] == 3
    assert status["modules_behind"] == 0

def test_student_get_status_with_missing_work(app_config: AppConfig):
    """Test status logic when the student has missing assignments."""
    student = Student("Doe, John", "jdoe@example.com", app_config)

    # Add a missing assignment for Module 2.
    # Assumes assignment_code_delimiter=" " and assignment_code_index=1 from conftest
    student.add_missing_assignment("CS1151 A2: Module 2 Assignment")
    student.add_missing_assignment("CS1151 Q2: Module 2 Quiz")

    status = student.get_status(current_module=4)

    assert status["nothing_late"] == 0
    assert status["last_module"] == 2
    assert status["modules_behind"] == 2  # Current (4) - Last (2)
    assert status["no_work_done"] == 0

def test_student_get_status_no_work_done(app_config: AppConfig):
    """Test status logic when the student is missing the very first assignment."""
    student = Student("Doe, John", "jdoe@example.com", app_config)

    # Missing the Q1a assignment flagged as first_assess_code in config
    student.add_missing_assignment("CS1151 Q1a: First Assessment")

    status = student.get_status(current_module=2)

    assert status["no_work_done"] == 1
    assert status["last_module"] == 1
