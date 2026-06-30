import pytest
import sys
from pathlib import Path

# Import the module to be tested
import courseStatus

def test_setup_base_path_exists(tmp_path, monkeypatch):
    """
    Test that setup_base_path returns a valid Path object
    when the target directory exists.
    """
    # Mock the global COURSE_PREFIX to ensure consistency in the test
    monkeypatch.setattr(courseStatus, "COURSE_PREFIX", "CS")
    course_number = 1411

    # Create the expected directory structure in the pytest temporary path
    expected_dir = tmp_path / f"{courseStatus.COURSE_PREFIX.lower()}{course_number}"
    expected_dir.mkdir()

    # Call the function
    result = courseStatus.setup_base_path(course_number, str(tmp_path))

    # Assertions
    assert result == expected_dir
    assert isinstance(result, Path)


def test_setup_base_path_not_exists(tmp_path, monkeypatch, capsys):
    """
    Test that setup_base_path exits with code 1 and prints an error
    when the target directory does not exist.
    """
    # Mock the global COURSE_PREFIX
    monkeypatch.setattr(courseStatus, "COURSE_PREFIX", "CS")
    course_number = 9999

    # We purposefully do NOT create the directory so it fails the .exists() check
    expected_dir = tmp_path / f"{courseStatus.COURSE_PREFIX.lower()}{course_number}"

    # Call the function and assert it raises SystemExit
    with pytest.raises(SystemExit) as exception_info:
        courseStatus.setup_base_path(course_number, str(tmp_path))

    # Check that it exited with status code 1
    assert exception_info.value.code == 1

    # Check standard error output for the correct error message
    captured = capsys.readouterr()
    expected_error_msg = f"ERROR: File storage path {expected_dir} must exist or be mounted!"
    assert expected_error_msg in captured.err
