import pytest
from pathlib import Path
from datetime import datetime, timedelta, time
from courseStatus import AppConfig, Assessment, Course


def test_appconfig_init(app_config: AppConfig) -> None:
    """Tests the initialization and parsing of the AppConfig class."""
    assert app_config.req_prefix == "CS"
    assert app_config.req_number == "1151"
    assert app_config.num_modules == 14
    assert "Feedback Survey" in app_config.non_academic
    assert len(app_config.raw_exclude_dates) == 7
    assert len(app_config.headers) > 0
    assert "d.university.edu" == app_config.domain
    assert "Student, Test" in app_config.ignored_students

    # Assert proper column headers are present
    assert app_config.grades_student_col == "Student"
    assert app_config.grades_email_col == "SIS Login ID"
    assert app_config.missing_student_col == "Student Name"
    assert app_config.missing_assignment_col == "Assignment Name"


def test_app_config_loads_dynamic_assessments(app_config: AppConfig):
    """Tests that all assessments, including dynamic/nonsense ones, are loaded into the registry."""
    assessments = Assessment._type_registry

    assert "Quizzes" in assessments
    assert "Assignments" in assessments
    assert "Geditr" in assessments

    geditr_meta = Assessment.get_meta("Geditr")
    assert geditr_meta is not None
    assert geditr_meta.due_time == time(2, 0)
    assert geditr_meta.due_day == "Saturday"
    assert geditr_meta.too_late_offset == timedelta(days=3)
    assert geditr_meta.resubmission_offset is None
    assert geditr_meta.final_due_time == time(4, 0)
    assert geditr_meta.final_due_day == "Tuesday"


def test_due_in_modules_expansion_for_dynamic_assessments(app_config: AppConfig):
    """Tests the shorthand parsing rules across different configurations."""
    geditr_meta = Assessment.get_meta("Geditr")
    assert geditr_meta is not None
    expected_geditr = [str(i) for i in range(1, 15)] + ["f"]
    assert geditr_meta.due_in_modules == expected_geditr

    quiz_meta = Assessment.get_meta("Quizzes")
    assert quiz_meta is not None
    assert quiz_meta.due_in_modules == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "f",
    ]


def test_due_in_modules_hyphen_only_expansion(app_config: AppConfig):
    """Tests that a single hyphen expands to all modules, excluding finals week."""
    expanded = app_config._expand_due_in_modules(["-"])
    expected = [str(i) for i in range(1, app_config.num_modules + 1)]

    assert expanded == expected
    assert "f" not in expanded


def test_bad_config_negative_too_late_offset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """Tests that a negative too_late_deadline_offset terminates the program with an error log."""
    config_content = """
    [Course]
    prefix = "CS"
    numbers = [1151]
    number_of_modules = 14
    [Course.Dates]
    dates = ["5-4", "9-1"]
    final_dates = ["9-4", "9-8"]
    [Course.Assessments.Quizzes]
    due_time = "5:00 PM"
    due_day = "Friday"
    due_in_modules = ["1-5"]
    too_late_deadline_offset = -2
    """

    config_home = tmp_path / ".config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    config_dir = config_home / "courseStatus"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "config.toml"
    config_path.write_text(config_content, encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        AppConfig("CS", "1151")

    assert excinfo.value.code == 1
    assert "invalid negative 'too_late_deadline_offset'" in caplog.text


def test_bad_config_exclude_date_out_of_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests that an exclude date completely outside the course term is gracefully ignored."""
    config_content = """
    [Course]
    prefix = "CS"
    numbers = [1151]
    number_of_modules = 14
    [Course.Dates]
    dates = ["5-4", "9-1"]
    final_dates = ["9-4", "9-8"]
    exclude_dates = ["12-12"]
    [Course.Assessments.Quizzes]
    due_time = "5:00 PM"
    due_day = "Friday"
    due_in_modules = ["1-5"]
    """

    config_home = tmp_path / ".config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    config_dir = config_home / "courseStatus"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / "config.toml"
    config_path.write_text(config_content, encoding="utf-8")

    config = AppConfig("CS", "1151")
    course = Course(config, 2026)

    mod1 = course.get_module(1)
    assert mod1 is not None

    quiz = mod1.get_assessment("Quizzes")
    assert quiz is not None
    assert quiz.due_date == datetime(2026, 5, 8, 17, 0)
