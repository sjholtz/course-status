from pathlib import Path
from datetime import time
from courseStatus import AppConfig, Assessment


def test_appconfig_init(mock_config_file: Path) -> None:
    """Tests the initialization and parsing of the AppConfig class."""
    config: AppConfig = AppConfig(str(mock_config_file))

    assert config.prefix == "CS"
    assert config.course_numbers == ["1151", "1411"]
    assert config.num_modules == 14
    assert Assessment.get_meta("Quizzes").due_time == time(17, 0)
    assert Assessment.get_meta("Quizzes").due_day == "Friday"
    assert Assessment.get_meta("Assignments").due_day == "Wednesday"
    assert "Feedback Survey" in config.non_academic
    assert len(config.raw_exclude_dates) == 6
    assert len(config.headers) > 0
    assert "FirstName" in config.headers
    assert "my.university.edu" == config.domain
