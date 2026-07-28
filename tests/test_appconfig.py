from pathlib import Path
from datetime import time
from courseStatus import AppConfig, Assessment


def test_appconfig_init(mock_config_file: Path) -> None:
    """Tests the initialization and parsing of the AppConfig class."""
    config: AppConfig = AppConfig(str(mock_config_file))

    assert config.prefix == "CS"
    assert config.course_numbers == ["1151", "1411"]
    assert config.num_modules == 14

    quizzes_meta = Assessment.get_meta("Quizzes")
    assert quizzes_meta is not None
    assert quizzes_meta.due_time == time(17, 0)
    assert quizzes_meta.due_day == "Friday"

    assignments_meta = Assessment.get_meta("Assignments")
    assert assignments_meta is not None
    assert assignments_meta.due_day == "Wednesday"

    assert "Feedback Survey" in config.non_academic
    assert len(config.raw_exclude_dates) == 6
    assert len(config.headers) > 0
    assert "First Name" in config.headers
    assert "d.university.edu" == config.domain
