import sys
import pytest
from unittest.mock import patch

import courseStatus

def test_parse_args_defaults():
    """Test that parse_args assigns the correct default values when no
    flags are provided.

    Note that this test fails if courseStatus.course_numbers is set to
    the empty list."""
    assert len(courseStatus.course_numbers) > 0

    test_args = ["courseStatus.py"]

    with patch.object(sys, "argv", test_args):
        args = courseStatus.parse_args()

        assert args.course == courseStatus.course_numbers[0]
        assert args.module is None
        assert args.date is None
        assert args.midterm is False
        assert args.base_path == courseStatus.default_base_path

def test_parse_args_custom_values():
    """Test that parse_args correctly captures and types explicitly
    provided flags.

    The patching of the courseStatus.course_numbers list ensures that
    the test will pass even if the user has set a different number of
    lists here."""
    with patch.object(courseStatus, 'course_numbers', ["1151", "1411"]):
        assert len(courseStatus.course_numbers) > 1

        test_args = [
            "courseStatus.py",
            "--course", courseStatus.course_numbers[1],
            "--module", "5",
            "--date", "03-15",
            "--midterm",
            "--base-path", "/custom/path/to/grades"
        ]

        with patch.object(sys, "argv", test_args):
            args = courseStatus.parse_args()

            assert args.course == courseStatus.course_numbers[1]
            assert args.module == 5
            assert args.date == "03-15"
            assert args.midterm is True
            assert args.base_path == "/custom/path/to/grades"

def test_parse_args_short_flags():
    """Test that parse_args correctly handles short flag
    equivalents.

    The patching of the courseStatus.course_numbers list ensures that
    the test will pass even if the user has set a different number of
    lists here."""
    with patch.object(courseStatus, 'course_numbers', ["1151", "1411"]):
        assert len(courseStatus.course_numbers) > 1

        test_args = [
            "courseStatus.py",
            "-c", courseStatus.course_numbers[1],
            "-m", "12",
            "-d", "11-01"
        ]

        with patch.object(sys, "argv", test_args):
            args = courseStatus.parse_args()

            assert args.course == courseStatus.course_numbers[1]
            assert args.module == 12
            assert args.date == "11-01"
            assert args.midterm is False
            assert args.base_path == courseStatus.default_base_path

def test_parse_args_invalid_course():
    """Test that parse_args exits when given an invalid choice for
    course.

    The patching of the courseStatus.course_numbers list ensures that
    the test will pass even if the user has set this to an empty
    list."""
    with patch.object(courseStatus, 'course_numbers', ["1151", "1411"]):
        test_args = ["courseStatus.py", "--course", "9999"]

        with patch.object(sys, "argv", test_args):
            # argparse calls sys.exit(2) on invalid choices
            with pytest.raises(SystemExit) as exception_info:
                courseStatus.parse_args()
            assert exception_info.value.code == 2

def test_parse_args_invalid_module_number():
    """Test that parse_args exits when the module number passed in is
    not an integer.

    The patching of the courseStatus.course_numbers list ensures that
    the test will pass even if the user has set this to an empty
    list.

    """
    with patch.object(courseStatus, 'course_numbers', ["1151", "1411"]):
        test_args = ["courseStatus.py", "--module", "five"]

        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exception_info:
                courseStatus.parse_args()
            assert exception_info.value.code == 2
