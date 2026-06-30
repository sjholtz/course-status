import pytest
import sys
import random
from pathlib import Path

import courseStatus


def test_setup_base_path_exists(tmp_path):
    """
    Test that setup_base_path returns a valid Path object
    when the target directory exists.
    """
    # Create the expected directory structure in the pytest temporary path
    expected_dir = (
        tmp_path
        / f"{courseStatus.COURSE_PREFIX.lower()}{courseStatus.COURSE_NUMBERS[0]}"
    )
    expected_dir.mkdir()

    # Call the function
    result = courseStatus.setup_base_path(courseStatus.COURSE_NUMBERS[0], str(tmp_path))

    # Assertions
    assert result == expected_dir
    assert isinstance(result, Path)


def test_setup_base_path_not_exists(tmp_path, capsys):
    """
    Test that setup_base_path exits with code 1 and prints an error
    when the target directory does not exist.
    """
    # Generate a random course number that is NOT in
    # courseStatus.COURSE_NUMBERS
    course_number = str(random.randint(9000, 9999))
    while course_number in courseStatus.COURSE_NUMBERS:
        course_number = str(random.randint(9000, 9999))

    # Purposefully do NOT create the directory so it fails the
    # .exists() check
    expected_dir = tmp_path / f"{courseStatus.COURSE_PREFIX.lower()}{course_number}"

    # Call the function and assert it raises SystemExit
    with pytest.raises(SystemExit) as exception_info:
        courseStatus.setup_base_path(course_number, str(tmp_path))

    # Check that it exited with status code 1
    assert exception_info.value.code == 1

    # Check standard error output for the correct error message
    captured = capsys.readouterr()
    expected_error_msg = (
        f"ERROR: File storage path {expected_dir} must exist or be mounted!"
    )
    assert expected_error_msg in captured.err
