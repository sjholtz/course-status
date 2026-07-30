#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

"""
Course Status Report Generator

This script processes Canvas gradebook exports and missing assignment reports
to generate a comprehensive CSV status report for students in a given course.
It uses a cascading cross-platform configuration setup (XDG_CONFIG_HOME or equivalents).

Usage:
    Initialize directories and base config:
        python courseStatus.py --init "~/Private/grades" -c CS 1151 -c MATH 1411

    Force override an existing global configuration file during initialization:
        python courseStatus.py --init "~/Private/grades" -c CS 1151 --force
        (Note: --force ONLY overwrites the global XDG config, local course configs are untouched).

    Generate a report:
        python courseStatus.py -c CS 1151 -m 4 --date 02-15 --midterm -v

Dependencies:
    - Python 3.11+ (required for standard library tomllib)
    - python-dateutil
"""

import os
import sys
import csv
import re
import pathlib
import argparse
import logging
import tomllib
import json
from datetime import datetime, date, timedelta, time
from typing import Any, Iterator, cast
from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU, WEEKLY, rrule, rruleset
from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta

# Configure basic logging for the CLI application
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

# Enforce Python 3.11+ to support native tomllib
if sys.hexversion < 0x030B0000:
    logger.critical("Must use Python version 3.11 or greater for TOML support.")
    sys.exit(1)

# Map string representations of weekdays from config.toml to dateutil constants
DAY_MAP: dict[str, Any] = {
    "Monday": MO,
    "Tuesday": TU,
    "Wednesday": WE,
    "Thursday": TH,
    "Friday": FR,
    "Saturday": SA,
    "Sunday": SU,
}

# Map target date relations to word synonym lists
RELATION_GROUPS: dict[str, list[str]] = {
    "next": ["next", "following", "upcoming"],
    "last": ["last", "previous", "prior", "past"],
    "this": ["this", "current"],
}

# Automatically build the lookup groups using dateutil constants as keys
WEEKDAY_GROUPS: dict[Any, list[str]] = {
    const: [name.lower()] for name, const in DAY_MAP.items()
}


DEFAULT_CONFIG_TEMPLATE = """[Course]
prefix = {prefix_val}
numbers = {numbers_val}
first_assess_code = "Q1a"
number_of_modules = 14
# Exact names or substrings in the Canvas export Name column to ignore
ignored_students = [
    "Points Possible",
    "Student, Test",
    "Test Student"
]

[Course.Dates]
# Dates MUST be in the form MM-DD, MM-D, M-DD, or M-D
# Term start and end dates, excluding finals week
dates = [
    "5-4",
    "9-1"
]
# Finals week start and end dates
final_dates = [
    "9-4",
    "9-8"
]
# Term dates that are normally class dates, where no class is held
exclude_dates = [
    "5-19",
    "7-9",
    "7-10",
    "7-11",
    "7-12",
    "7-13"
]

[Course.Assessments]
non_academic = [
    "Feedback Survey",
    "Introductory Quiz"
]
[Course.Assessments.Quizzes]
due_time = "5:00 PM"
due_day = "Friday"
# Days until too late to turn in
too_late_deadline_offset = 14
due_in_modules = ["1-5", "f"]
final_due_time = "12:00 PM"
final_due_day = "Monday"
[Course.Assessments.Quizzes.Adjustments]
# Dynamic rules to adjust specific due dates. First column: An
# existing due date or a module number. Second column: Shifted due
# date.
# Examples:
# "11-27" = "11-25"
# "4" = "11-25"
# "11-27" = "next Monday"
# "3" = "+2 days"

[Course.Assessments.Assignments]
due_time = "5:00 PM"
due_day = "Wednesday"
# Days until too late to turn in
too_late_deadline_offset = 14
# Days until too late to resubmit updated solution
resubmission_deadline_offset = 21
due_in_modules = ["1-2", "5-7", "f"]
final_due_time = "5:00 PM"
final_due_day = "Friday"

[System]
base_path = {base_path_val}
# Keywords used to identify the correct CSV files for a given date
grades_file_keyword = "Grades"
missing_file_keyword = "missingAssignments"
output_file_prefix = "status-"

# Canvas CSV Header Mappings
grades_student_col = "Student"
grades_email_col = "SIS Login ID"
missing_student_col = "Student Name"
missing_assignment_col = "Assignment Name"

# Assignment Code Extraction Settings
assignment_code_delimiter = " "
assignment_code_index = 1

[Mail_Merge]
domain = "d.university.edu"
headers = [
    "Course",
    "First Name",
    "Last Name",
    "Email",
    "As Of Date",
    "Midterm Alert",
    "Modules Behind",
    "Last Module",
    "Current Module",
    "No Work Done",
    "Nothing Late",
    "Quiz Late",
    "Quiz Late Date",
    "Assign Late",
    "Assign Late Date",
    "Resubmit",
    "Resubmit Date"
]
date_format = "%-I:%M %p on %A %-d %B %Y"
"""

LOCAL_CONFIG_SKELETON = """# Local Course Override Configuration
# Values specified here will override values in global
# config. Uncomment by removing the "# " and change the value to the
# right of the equal sign (=).

# Commonly overridden key/values shown. See other key/values in global
# config that you can add here. Be sure that:
# 1. You include the square bracketed section title, if it is not
#    included here
# 2. Place the key = value pair under the same square bracketed
#    section title here as it occurs in the global config

# WARNING: 'base_path', 'prefix', and 'numbers' are omitted here and
# MUST NOT be overridden here.

# [Course]
# first_assess_code = "Q1a"
# number_of_modules = 14
# # Exact names or substrings in the Canvas Grades export 'Name'
# # column to ignore
# ignored_students = [
#     "Student, Test",
#     "Test Student"
# ]

# [Course.Assessments]
# non_academic = [
#     "Feedback Survey",
#     "Introductory Quiz"
# ]

# # The category and its keys below can repeat for other assessment
# # names: Exams, Quizzes, Labs, Discussions—Anything that is worth
# # points and has a due date/time.
#
# [Course.Assessments.<AssessmentName>]
# due_time = "5:00 PM"
# due_day = "Friday"
# Examples of module specification
# due_in_modules = ["1-5", "f"] # Modules 1-5 and finals week
# due_in_modules = ["-2", "5-7"] # Modules 1, 2, 5, 6, 7
# due_in_modules = ["2-"] # Modules 2 through end except for finals week
# due_in_modules = ["2-f"] # Modules 2 through end and finals week
# due_in_modules = ["-"] # All modules except for finals week
# # Days until too late to turn in—Omit for assessment that has no
# # late submission date
# too_late_deadline_offset = 14
# # Days until too late to resubmit updated solution—Omit for
# # assessment that cannot be resubmitted
# resubmission_deadline_offset = 21
# # Only supply the keys below for assessments that are due during
# # finals week, i.e. they have an "f" in their 'due_in_module' key
# # above
# final_due_time = "12:00 PM"
# final_due_day = "Monday"
# [Course.Assessments.<AssessmentName>.Adjustments]
# "11-27" = "11-25"
# "3" = "next wednesday"

# [Mail_Merge]
# headers = [
#     "Course",
#     "First Name",
#     "Last Name",
#     "Email",
#     "As Of Date",
#     "Midterm Alert",
#     "Modules Behind",
#     "Last Module",
#     "Current Module",
#     "No Work Done",
#     "Nothing Late"
# ]
"""


def get_config_home() -> pathlib.Path:
    """Returns the cross-platform configuration directory base."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return pathlib.Path(xdg_config_home)

    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return pathlib.Path(appdata)
        return pathlib.Path.home() / "AppData" / "Roaming"

    # macOS and Linux fallback
    return pathlib.Path.home() / ".config"


def deep_merge(base: dict, update: dict, path: list[Any] | None = None) -> dict:
    """Recursively merges dictionary `update` into `base`."""
    if path is None:
        path = []
    for key, val in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            deep_merge(base[key], val, path + [str(key)])
        else:
            base[key] = val
    return base


class AssessmentMeta:
    """Stores the definitive configuration and rules for a specific assessment type."""

    def __init__(
        self,
        due_time: time,
        due_day: str,
        due_in_modules: list[str],
        too_late_offset: timedelta | None = None,
        resubmission_offset: timedelta | None = None,
        final_due_time: time | None = None,
        final_due_day: str | None = None,
        shifted_dates: dict[str, str] | None = None,
    ) -> None:
        self.due_time: time = due_time
        self.due_day: str = due_day
        self.due_in_modules: list[str] = due_in_modules
        self.too_late_offset: timedelta | None = too_late_offset
        self.resubmission_offset: timedelta | None = resubmission_offset
        self.final_due_time: time | None = final_due_time
        self.final_due_day: str | None = final_due_day
        self.shifted_dates: dict[str, str] = shifted_dates or {}


class Assessment:
    """Represents an individual assessment that counts toward a student's grade."""

    # Class-level registry acting as the meta-class storage for each assessment 'type'
    _type_registry: dict[str, AssessmentMeta] = {}

    @classmethod
    def register_type_meta(
        cls,
        assess_type: str,
        due_time: time,
        due_day: str,
        due_in_modules: list[str],
        too_late_offset: timedelta | None = None,
        resubmission_offset: timedelta | None = None,
        final_due_time: time | None = None,
        final_due_day: str | None = None,
        shifted_dates: dict[str, str] | None = None,
    ) -> None:
        """Registers the meta-information for a specific assessment type."""
        cls._type_registry[assess_type] = AssessmentMeta(
            due_time,
            due_day,
            due_in_modules,
            too_late_offset,
            resubmission_offset,
            final_due_time,
            final_due_day,
            shifted_dates,
        )

    @classmethod
    def get_meta(cls, assess_type: str) -> AssessmentMeta | None:
        return cls._type_registry.get(assess_type)

    def __init__(
        self,
        assess_type: str,
        due_date: datetime,
        strict_validation: bool = False,
        is_final: bool = False,
    ) -> None:
        self.type: str = assess_type
        self.due_date: datetime = due_date
        self.is_final: bool = is_final

        # Retrieve the meta-information for this specific assessment type
        meta: AssessmentMeta | None = self._type_registry.get(self.type)
        if not meta:
            raise ValueError(
                f"Assessment type '{self.type}' is missing meta-configuration."
            )

        # Validate the schedule
        self._validate_schedule(meta, strict_validation, self.is_final)

        self.too_late_date: datetime | None = None
        self.resubmission_date: datetime | None = None

        # Calculate deadline attributes dynamically based on the stored durations.
        # Only apply these offsets if this is NOT a finals week assessment.
        if not self.is_final:
            if meta.too_late_offset is not None:
                self.too_late_date = self.due_date + meta.too_late_offset

            if meta.resubmission_offset is not None:
                self.resubmission_date = self.due_date + meta.resubmission_offset

    def _validate_schedule(
        self, meta: AssessmentMeta, strict: bool, is_final: bool
    ) -> None:
        """Validates that the provided due_date aligns with the registered meta rules."""

        expected_time = (
            meta.final_due_time if is_final and meta.final_due_time else meta.due_time
        )
        expected_day = (
            meta.final_due_day if is_final and meta.final_due_day else meta.due_day
        )

        # Validate time
        if self.due_date.time() != expected_time:
            msg = f"{self.type} scheduled at {self.due_date.time()}, but expects {expected_time}."
            if strict:
                raise ValueError(msg)
            logger.debug(f"Schedule override: {msg}")

        # Validate day of week (strftime('%A') returns the full weekday name)
        actual_day = self.due_date.strftime("%A")
        if actual_day != expected_day:
            msg = f"{self.type} scheduled on {actual_day}, but expects {expected_day}."
            if strict:
                raise ValueError(msg)
            logger.debug(f"Schedule override: {msg}")

    def __repr__(self) -> str:
        return f"<Assessment(type='{self.type}', due_date={self.due_date.strftime('%Y-%m-%d %H:%M')}, final={self.is_final})>"


class AppConfig:
    """Parses and stores settings merged from global and local configurations."""

    def __init__(self, req_prefix: str, req_number: str) -> None:
        self.req_prefix = req_prefix.upper()
        self.req_number = str(req_number)

        self.config_dir: pathlib.Path = get_config_home() / "courseStatus"
        global_config_path: pathlib.Path = self.config_dir / "config.toml"

        if not global_config_path.is_file():
            logger.error(f"Global configuration not found at '{global_config_path}'")
            logger.error("Please run the tool with --init first.")
            sys.exit(1)

        try:
            global_data: dict[str, Any] = tomllib.loads(
                global_config_path.read_text(encoding="utf-8")
            )
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error parsing global TOML config: {e}")
            sys.exit(1)

        self._validate_course_registration(global_data)

        raw_base_path = global_data.get("System", {}).get(
            "base_path", "~/Private/grades"
        )
        self.base_path_obj = pathlib.Path(raw_base_path).expanduser()

        # Attempt to load local course config
        local_config_path = (
            self.base_path_obj
            / f"{self.req_prefix.lower()}{self.req_number}"
            / "config.toml"
        )
        if local_config_path.is_file():
            try:
                local_data: dict[str, Any] = tomllib.loads(
                    local_config_path.read_text(encoding="utf-8")
                )
                self._strip_restricted_keys(local_data, local_config_path)
                logger.debug(
                    f"Applying local config overrides from {local_config_path}"
                )
                global_data = deep_merge(global_data, local_data)
            except tomllib.TOMLDecodeError as e:
                logger.error(
                    f"Error parsing local TOML config at '{local_config_path}': {e}"
                )
                sys.exit(1)

        self._load_from_dict(global_data)

    def _validate_course_registration(self, global_data: dict[str, Any]) -> None:
        """Validates that the requested prefix and number are registered in the global config."""
        course_data = global_data.get("Course", {})
        conf_prefix = course_data.get("prefix", "")
        conf_numbers = [str(n) for n in course_data.get("numbers", [])]

        valid = False
        avail_courses = []

        if isinstance(conf_prefix, list):
            if len(conf_prefix) != len(conf_numbers):
                logger.error(
                    "Global config Error: 'prefix' and 'numbers' lists must be the same length."
                )
                sys.exit(1)
            for p, n in zip(conf_prefix, conf_numbers):
                avail_courses.append(f"{p} {n}")
                if p.upper() == self.req_prefix and n == self.req_number:
                    valid = True
        elif isinstance(conf_prefix, str):
            for n in conf_numbers:
                avail_courses.append(f"{conf_prefix} {n}")
                if conf_prefix.upper() == self.req_prefix and n == self.req_number:
                    valid = True

        if not valid:
            logger.error(
                f"Course '{self.req_prefix} {self.req_number}' is not registered in the global config."
            )
            logger.error(f"Global Config Path: {self.config_dir / 'config.toml'}")
            logger.error(
                f"Available Courses: {', '.join(avail_courses) if avail_courses else 'None found'}"
            )
            sys.exit(1)

    def _strip_restricted_keys(
        self, local_data: dict[str, Any], filepath: pathlib.Path
    ) -> None:
        """Removes protected keys from local configs before merging and warns the user."""
        stripped = False

        if "Course" in local_data:
            if "prefix" in local_data["Course"]:
                local_data["Course"].pop("prefix")
                stripped = True
            if "numbers" in local_data["Course"]:
                local_data["Course"].pop("numbers")
                stripped = True

        if "System" in local_data and "base_path" in local_data["System"]:
            local_data["System"].pop("base_path")
            stripped = True

        if stripped:
            logger.warning(
                f"Restricted keys ('prefix', 'numbers', 'base_path') found in local config '{filepath}'. They were ignored."
            )

    def _load_from_dict(self, config_data: dict[str, Any]) -> None:
        """Loads configuration variables identically to previous native behavior natively, providing fallbacks."""
        course_data: dict[str, Any] = config_data.get("Course", {})
        dates_data: dict[str, Any] = course_data.get("Dates", {})
        assessment_data: dict[str, Any] = course_data.get("Assessments", {})
        system_data: dict[str, Any] = config_data.get("System", {})
        mail_merge_data: dict[str, Any] = config_data.get("Mail_Merge", {})

        # Set specific active course string equivalents
        self.active_prefix: str = self.req_prefix
        self.active_number: str = self.req_number
        self.first_assess_code: str = course_data.get("first_assess_code", "Q1a")
        self.num_modules: int = course_data.get("number_of_modules", 14)
        self.non_academic: list[str] = assessment_data.get(
            "non_academic", ["Feedback Survey"]
        )
        self.ignored_students: list[str] = course_data.get(
            "ignored_students", ["Points Possible", "Student, Test"]
        )

        # Base dates
        self.raw_dates: list[str] = dates_data.get("dates", ["1-1", "12-31"])
        self.raw_exclude_dates: list[str] = dates_data.get("exclude_dates", [])
        self.raw_final_dates: list[str] = dates_data.get("final_dates", [])

        # Validate the dates extracted from the config
        self._validate_dates()

        self.grades_keyword: str = system_data.get("grades_file_keyword", "Grades")
        self.missing_keyword: str = system_data.get(
            "missing_file_keyword", "missingAssignments"
        )
        self.output_prefix: str = system_data.get("output_file_prefix", "status-")

        # Load column headers
        self.grades_student_col: str = system_data.get("grades_student_col", "Student")
        self.grades_email_col: str = system_data.get("grades_email_col", "SIS Login ID")
        self.missing_student_col: str = system_data.get(
            "missing_student_col", "Student Name"
        )
        self.missing_assignment_col: str = system_data.get(
            "missing_assignment_col", "Assignment Name"
        )

        self.assign_code_index: int = system_data.get("assignment_code_index", 1)
        raw_delimiter: str = system_data.get("assignment_code_delimiter", " ")
        # Map a single space to None so Python's split() handles consecutive whitespace safely
        self.assign_code_delimiter: str | None = (
            None if raw_delimiter == " " else raw_delimiter
        )

        # Load [Mail_Merge] variables natively
        self.headers: list[str] = mail_merge_data.get(
            "headers", ["Course", "Name", "Status"]
        )
        # Fallback to "preferred-domain.edu" if not provided in config
        self.domain: str = mail_merge_data.get("domain", "preferred-domain.edu")
        raw_format: str = mail_merge_data.get(
            "date_format", "%-I:%M %p on %A %-d %B %Y"
        )

        # Make custom datetime parsing cross-platform
        self.date_format: str
        if os.name == "nt":  # Windows environment
            self.date_format = raw_format.replace("%-", "%#")
        else:  # Unix/Linux/macOS environment
            self.date_format = raw_format.replace("%#", "%-")

        # Parse and register assessment configurations
        self._load_assessments(course_data.get("Assessments", {}), mail_merge_data)

    def _expand_due_in_modules(self, raw_modules: list[str]) -> list[str]:
        """Expands shorthand range formats in due_in_modules strings."""
        expanded: list[str] = []
        for item in raw_modules:
            item = item.strip().lower()
            if "-" in item:
                parts = item.split("-")
                if len(parts) == 2:
                    start_str, end_str = parts[0].strip(), parts[1].strip()

                    # Determine start index
                    try:
                        start_idx = 1 if not start_str else int(start_str)
                    except ValueError:
                        logger.error(f"Invalid range start in '{item}'.")
                        sys.exit(1)

                    include_f = False
                    # Determine end index and inclusion of finals 'f'
                    if not end_str:
                        end_idx = self.num_modules
                    elif end_str == "f":
                        end_idx = self.num_modules
                        include_f = True
                    else:
                        try:
                            end_idx = int(end_str)
                        except ValueError:
                            logger.error(f"Invalid range end in '{item}'.")
                            sys.exit(1)

                    # Append numbers in range
                    for i in range(start_idx, end_idx + 1):
                        expanded.append(str(i))
                    if include_f:
                        expanded.append("f")
                else:
                    logger.error(f"Invalid module range format: '{item}'")
                    sys.exit(1)
            else:
                # Add standalone module indicator
                expanded.append(item)

        # Remove duplicates while preserving original order
        seen = set()
        result = []
        for x in expanded:
            if not x in seen:
                seen.add(x)
                result.append(x)

        return result

    def _load_assessments(
        self, assessments_data: dict[str, Any], mail_merge_data: dict[str, Any]
    ) -> None:
        """Parses the nested assessment data and registers types into the Assessment class."""

        # Clear registry for clean state in testing environments
        Assessment._type_registry.clear()

        for assess_type, assess_config in assessments_data.items():
            # Silently skip non-academic list as it is handled elsewhere
            if assess_type == "non_academic" or assess_type == "late_header_suffix":
                continue

            if not isinstance(assess_config, dict):
                logger.warning(f"Skipping invalid assessment entry: '{assess_type}'")
                continue

            raw_time: str | None = assess_config.get("due_time")
            due_day: str | None = assess_config.get("due_day")
            due_in_modules_raw: list[str] | None = assess_config.get("due_in_modules")

            if raw_time is None or due_day is None or due_in_modules_raw is None:
                logger.error(
                    f"Assessment '{assess_type}' is missing required 'due_time', 'due_day', or 'due_in_modules' in config.toml."
                )
                sys.exit(1)

            # Expand potential shorthand formats from the configuration
            due_in_modules = self._expand_due_in_modules(due_in_modules_raw)

            # Add this assessment to the header
            self.headers.append(
                f"{assess_type} {mail_merge_data.get('assessment_too_late_header_suffix')}"
            )

            parsed_time: time = datetime.strptime(raw_time.upper(), "%I:%M %p").time()

            # Retrieve offsets and explicitly handle negative and zero values
            tl_offset: int | None = assess_config.get("too_late_deadline_offset")
            if tl_offset is not None:
                if tl_offset < 0:
                    logger.error(
                        f"Assessment '{assess_type}' has an invalid negative 'too_late_deadline_offset': {tl_offset}."
                    )
                    sys.exit(1)
                elif tl_offset == 0:
                    tl_offset = None
                else:
                    # Append assessment too late to header
                    self.headers.append(
                        f"{assess_type} {mail_merge_data.get('assessment_too_late_date_header_suffix')}"
                    )

            rs_offset: int | None = assess_config.get("resubmission_deadline_offset")
            if rs_offset is not None:
                if rs_offset < 0:
                    logger.error(
                        f"Assessment '{assess_type}' has an invalid negative 'resubmission_deadline_offset': {rs_offset}."
                    )
                    sys.exit(1)
                elif rs_offset == 0:
                    rs_offset = None
                else:
                    # Append assessment resubmit to header
                    self.headers.append(
                        f"{assess_type} {mail_merge_data.get('assessment_resubmit_header_suffix')}"
                    )
                    self.headers.append(
                        f"{assess_type} {mail_merge_data.get('assessment_resubmit_date_header_suffix')}"
                    )

            too_late: timedelta | None = (
                timedelta(days=tl_offset) if tl_offset is not None else None
            )
            resubmit: timedelta | None = (
                timedelta(days=rs_offset) if rs_offset is not None else None
            )

            final_due_time_raw: str | None = assess_config.get("final_due_time")
            final_due_day: str | None = assess_config.get("final_due_day")
            final_due_time: time | None = (
                datetime.strptime(final_due_time_raw.upper(), "%I:%M %p").time()
                if final_due_time_raw
                else None
            )
            shifted_dates: dict[str, str] = assess_config.get("Adjustments", {})

            Assessment.register_type_meta(
                assess_type,
                parsed_time,
                due_day,
                due_in_modules,
                too_late,
                resubmit,
                final_due_time,
                final_due_day,
                shifted_dates,
            )

    def _validate_dates(self) -> None:
        """Validates that dates provided in config are in M-D or MM-DD format and are valid calendar days."""
        if len(self.raw_dates) != 2:
            logger.error(
                f"Config 'dates' must contain exactly two elements (start and end). Found {len(self.raw_dates)}."
            )
            sys.exit(1)

        if len(self.raw_final_dates) != 2:
            logger.error(
                f"Config 'final_dates' must contain exactly two elements (start and end). Found {len(self.raw_final_dates)}."
            )
            sys.exit(1)

        def check_date(date_str: str) -> None:
            try:
                m, d = map(int, date_str.split("-"))
                # Use a leap year (e.g., 2024) to validate M and D bounds, natively allowing Feb 29
                datetime(2024, m, d)
            except ValueError:
                logger.error(f"Invalid date format '{date_str}'.")
                sys.exit(1)

        for d_str in self.raw_dates + self.raw_final_dates + self.raw_exclude_dates:
            check_date(d_str)


class CourseModule:
    """Holds a singular module and its associated assessments."""

    def __init__(self, number: int | str) -> None:
        self.number: int | str = number
        self.assessments: dict[str, Assessment] = {}

    def add_assessment(self, assess: Assessment) -> None:
        self.assessments[assess.type] = assess

    def get_assessment(self, assess_type: str) -> Assessment | None:
        return self.assessments.get(assess_type)


class Course:
    """Aggregates CourseModule objects and supports module lookup and iteration."""

    _OFFSET_PATTERN = re.compile(r"^([+-]?\d+)\s*(d|day|days)?$")

    def __init__(self, config: AppConfig, year: int) -> None:
        self.config: AppConfig = config
        self.year: int = year
        self.modules: dict[int | str, CourseModule] = {}
        self._initialize_modules()

    def _adjust_year_wrap(
        self, target_dt: datetime, reference_dt: datetime
    ) -> datetime:
        """Centralized helper to adjust the year if the target logically wraps into the next year."""
        if target_dt < reference_dt and target_dt.month < reference_dt.month:
            return target_dt.replace(year=self.year + 1)
        return target_dt

    def _parse_term_dates(self) -> tuple[datetime, datetime]:
        """Parses and calculates the base term start and end dates."""
        start_m, start_d = map(int, self.config.raw_dates[0].split("-"))
        end_m, end_d = map(int, self.config.raw_dates[1].split("-"))

        # Build base term dates (times will be adjusted per assessment type)
        base_start: datetime = datetime(self.year, start_m, start_d)
        base_end: datetime = datetime(self.year, end_m, end_d)

        if base_end < base_start:
            base_end = base_end.replace(year=self.year + 1)

        return base_start, base_end

    def _parse_finals_dates(self, base_start: datetime) -> tuple[datetime, datetime]:
        """Parses and calculates the finals week start and end dates."""
        # Build finals week dates
        f_start_m, f_start_d = map(int, self.config.raw_final_dates[0].split("-"))
        f_end_m, f_end_d = map(int, self.config.raw_final_dates[1].split("-"))

        final_start: datetime = datetime(self.year, f_start_m, f_start_d)
        final_end: datetime = datetime(self.year, f_end_m, f_end_d)

        if final_end < final_start:
            final_end = final_end.replace(year=self.year + 1)
        if final_start < base_start and final_start.month < base_start.month:
            final_start = final_start.replace(year=self.year + 1)
            final_end = final_end.replace(year=self.year + 1)

        return final_start, final_end

    def _parse_exclusion_dates(
        self, base_start: datetime, base_end: datetime
    ) -> list[datetime]:
        """Parses individual exclusion dates and handles term wrapping."""
        # Parse exclusion dates
        exdates: list[datetime] = []
        for ex_str in self.config.raw_exclude_dates:
            ex_m, ex_d = map(int, ex_str.split("-"))
            ex_dt: datetime = datetime(self.year, ex_m, ex_d)
            if ex_dt < base_start and base_end.year > self.year:
                ex_dt = ex_dt.replace(year=self.year + 1)
            exdates.append(ex_dt)
        return exdates

    def _expand_module_ranges(self, due_in_modules: list[str]) -> list[str]:
        """Expands shorthand configuration ranges (e.g., '1-14', '-3', '13-') into explicit string identifiers."""
        expanded: list[str] = []
        for mod_val in due_in_modules:
            mod_val = mod_val.strip().lower()

            if mod_val == "f":
                expanded.append("f")
            elif "-" in mod_val:
                parts = mod_val.split("-")
                start_str = parts[0].strip()
                end_str = parts[1].strip() if len(parts) > 1 else ""

                try:
                    # Default to 1 if no start is provided (e.g., "-3")
                    start = int(start_str) if start_str else 1
                    # Default to total modules if no end is provided (e.g., "13-")
                    end = int(end_str) if end_str else self.config.num_modules

                    for i in range(start, end + 1):
                        expanded.append(str(i))
                except ValueError:
                    logger.warning(
                        f"Invalid module range format '{mod_val}'. Skipping."
                    )
            else:
                expanded.append(mod_val)

        return expanded

    def _resolve_keyword(self, token: str, groups: dict[Any, list[str]]) -> Any:
        """Dynamically matches a prefix token against grouped full-word synonyms found in groups."""
        # Strip non-alphabetical characters and lowercase for safer matching
        token = re.sub(r"[^a-zA-Z]", "", token).lower()

        # Find groups where at least one word starts with `token`
        matched_groups = {
            group: [word for word in words if word.startswith(token)]
            for group, words in groups.items()
            if any(word.startswith(token) for word in words)
        }

        if len(matched_groups) == 1:
            return next(iter(matched_groups.keys()))
        elif len(matched_groups) == 0:
            raise ValueError(f"Unrecognized prefix/keyword: '{token}'")
        else:
            conflicts = list(matched_groups.keys())
            raise ValueError(
                f"Ambiguous token '{token}' matches multiple options: {conflicts}"
            )

    def _resolve_base_date(
        self,
        key: int | str,
        module_dates: dict[int, datetime],
        default_year: int | None = None,
    ) -> datetime:
        """
        Determines the reference date for a TOML key.
        - If key is an int/numeric string (e.g. 3 or "3"), looks up Module N's date.
        - If key is a date string (e.g. "6/4"), parses it directly as a date.
        """
        str_key = str(key).strip()

        # Case A: Key is a Module Number
        if str_key.isdigit():
            mod_num = int(str_key)
            if mod_num not in module_dates:
                raise KeyError(
                    f"Module number {mod_num} not found in scheduled course dates."
                )
            return module_dates[mod_num]

        # Case B: Key is a Date String (e.g., "6/4", "2026-06-04")
        try:
            parsed_dt = parse_date(str_key)
            if (
                default_year
                and parsed_dt.year == datetime.now().year
                and str(default_year) not in str_key
            ):
                parsed_dt = parsed_dt.replace(year=default_year)
            return parsed_dt
        except Exception as e:
            raise ValueError(
                f"Could not parse key '{key}' as a module ID or date string."
            ) from e

    def _apply_rule(self, base_dt: datetime, rule_str: str) -> datetime:
        """
        Parses and applies a relative rule or exact date string to a base date.
        Supports:
          - Relative Offset:  "+3 days", "-1d", "+2"
          - Relative Weekday: "next Monday", "n mo", "following th", "last fri", "this tu"
          - Exact Date Override: "06-04", "6/4/2026"
        """
        cleaned_rule = rule_str.strip().lower()

        # 1. Check for day offsets (e.g., "+3 days", "-1d", "+2")
        offset_match = self._OFFSET_PATTERN.match(cleaned_rule)
        if offset_match:
            days_delta = int(offset_match.group(1))
            return base_dt + relativedelta(days=days_delta)

        # 2. Check for relative weekdays (e.g., "next monday", "n mo")
        tokens = [t for t in cleaned_rule.split() if t not in ("the", "on")]
        if len(tokens) == 2:
            try:
                relation = self._resolve_keyword(tokens[0], RELATION_GROUPS)
                target_day = self._resolve_keyword(tokens[1], WEEKDAY_GROUPS)

                if relation == "next":
                    # Jump to next occurrence of target weekday
                    return base_dt + relativedelta(days=+1, weekday=target_day)
                elif relation == "last":
                    # Jump to previous occurrence of target weekday
                    return base_dt + relativedelta(days=-1, weekday=target_day(-1))
                elif relation == "this":
                    # Jump to occurrence of target weekday within the current week
                    return base_dt + relativedelta(weekday=target_day)
            except ValueError:
                pass  # Fall through to exact date parsing if token resolution fails

        # 3. Fallback: Parse as explicit target date string
        try:
            parsed_target = parse_date(cleaned_rule)
            # If the user didn't explicitly type a year (meaning the parser guessed the current year)
            if (
                parsed_target.year == datetime.now().year
                and str(parsed_target.year) not in cleaned_rule
            ):
                # Default to the base date's year
                parsed_target = parsed_target.replace(year=base_dt.year)
                # Apply Course year-wrap logic centrally
                parsed_target = self._adjust_year_wrap(parsed_target, base_dt)

            return parsed_target
        except Exception as e:
            raise ValueError(
                f"Unable to parse relative rule or date string: '{rule_str}'"
            ) from e

    def _resolve_override_date(
        self, key: int | str, value: str, module_dates: dict[int, datetime]
    ) -> datetime:
        """Resolves a TOML key-value pair into a finalized datetime object."""
        base_dt = self._resolve_base_date(key, module_dates, default_year=self.year)
        return self._apply_rule(base_dt, value)

    def _generate_assessment_dates(
        self,
        assess_type: str,
        meta: AssessmentMeta,
        start: datetime,
        end: datetime,
        exdates: list[datetime],
    ) -> list[datetime]:
        """Generates the standard weekly recurrence rules and processes dynamic overrides."""
        due_day_const = DAY_MAP.get(meta.due_day, FR)
        type_start = start.replace(hour=meta.due_time.hour, minute=meta.due_time.minute)
        type_end = end.replace(hour=meta.due_time.hour, minute=meta.due_time.minute)

        # Pre-calculate which raw dates are being targeted by explicit overrides
        # so we don't accidentally drop them when compiling the base sequence.
        targeted_base_dates = set()
        for key in meta.shifted_dates.keys():
            str_key = str(key).strip()
            if not str_key.isdigit():
                try:
                    parsed_dt = parse_date(str_key)
                    if (
                        parsed_dt.year == datetime.now().year
                        and str(self.year) not in str_key
                    ):
                        parsed_dt = parsed_dt.replace(year=self.year)
                    targeted_base_dates.add(parsed_dt.date())
                except Exception:
                    pass

        # 1. Generate base recurring schedule ignoring exclusions for a moment
        rules = rruleset()
        rules.rrule(
            rrule(WEEKLY, byweekday=due_day_const, dtstart=type_start, until=type_end)
        )

        type_dates: list[datetime] = []

        # 2. Extract specific dates, manually processing exclusions
        for dt in list(rules):
            if len(type_dates) == self.config.num_modules:
                break

            is_exdate = any(ex.date() == dt.date() for ex in exdates)
            targeted_by_date = dt.date() in targeted_base_dates

            current_mod_index = len(type_dates) + 1
            targeted_by_mod = str(current_mod_index) in meta.shifted_dates

            # If it's an excluded date and NOT explicitly targeted by an adjustment, skip it
            if is_exdate and not (targeted_by_date or targeted_by_mod):
                continue

            type_dates.append(dt)

        # 3. Build mapping of module numbers to calculated dates
        module_dates = {i + 1: dt for i, dt in enumerate(type_dates)}

        # 4. Resolve and apply all adjustments dynamically
        for key, rule_str in meta.shifted_dates.items():
            try:
                new_dt = self._resolve_override_date(key, rule_str, module_dates)

                # Re-apply the target hour and minute since user strings usually omit them
                new_dt = new_dt.replace(
                    hour=meta.due_time.hour, minute=meta.due_time.minute
                )

                # Validation 1: Between course start and end dates
                if not (start.date() <= new_dt.date() <= end.date()):
                    logger.error(
                        f"Shifted date value '{new_dt.date()}' for {assess_type} is not within course start and end dates."
                    )
                    sys.exit(1)

                # Validation 2: Warn if it lands squarely on a globally excluded date
                if any(ex.date() == new_dt.date() for ex in exdates):
                    logger.warning(
                        f"Shifted date '{new_dt.date()}' for {assess_type} falls on a globally excluded date."
                    )

                # Assign back to sequence
                if str(key).strip().isdigit():
                    mod_idx = int(str(key).strip()) - 1
                    type_dates[mod_idx] = new_dt
                else:
                    base_dt = self._resolve_base_date(
                        key, module_dates, default_year=self.year
                    )
                    for i, current_dt in enumerate(type_dates):
                        if current_dt.date() == base_dt.date():
                            type_dates[i] = new_dt
                            break

            except Exception as e:
                logger.error(
                    f"Error processing adjustment '{key} = \"{rule_str}\"' for {assess_type}: {e}"
                )
                sys.exit(1)

        return type_dates

    def _schedule_final_assessment(
        self,
        assess_type: str,
        meta: AssessmentMeta,
        final_start: datetime,
        final_end: datetime,
    ) -> None:
        """Determines the specific final week date and assigns it to the 'f' module."""
        if not meta.final_due_day or not meta.final_due_time:
            logger.error(
                f"Assessment '{assess_type}' specifies 'f' but is missing final_due_day or final_due_time."
            )
            sys.exit(1)

        final_day_const = DAY_MAP.get(meta.final_due_day, FR)
        f_start = final_start.replace(
            hour=meta.final_due_time.hour, minute=meta.final_due_time.minute
        )
        f_end = final_end.replace(
            hour=meta.final_due_time.hour, minute=meta.final_due_time.minute
        )

        f_rules = rrule(WEEKLY, byweekday=final_day_const, dtstart=f_start, until=f_end)
        f_dates = list(f_rules)

        if not f_dates:
            logger.error(
                f"Could not find a {meta.final_due_day} during finals week for {assess_type}."
            )
            sys.exit(1)

        if "f" not in self.modules:
            self.modules["f"] = CourseModule("f")
        self.modules["f"].add_assessment(
            Assessment(assess_type, f_dates[0], is_final=True)
        )

    def _schedule_standard_assessment(
        self, assess_type: str, mod_val: str, type_dates: list[datetime]
    ) -> None:
        """Matches a standard assessment with its corresponding date and assigns it to a numbered module."""
        try:
            mod_int = int(mod_val)
        except ValueError:
            logger.warning(
                f"Invalid module identifier '{mod_val}' in {assess_type} config. Skipping."
            )
            return

        if 1 <= mod_int <= len(type_dates):
            if mod_int not in self.modules:
                self.modules[mod_int] = CourseModule(mod_int)
            self.modules[mod_int].add_assessment(
                Assessment(assess_type, type_dates[mod_int - 1])
            )

    def _initialize_modules(self) -> None:
        """Coordinates the initialization of all modules and their respective assessments."""
        base_start, base_end = self._parse_term_dates()
        final_start, final_end = self._parse_finals_dates(base_start)
        exdates = self._parse_exclusion_dates(base_start, base_end)

        # Iterate over all registered assessment types to dynamically build schedules
        for assess_type, meta in Assessment._type_registry.items():
            if not meta.due_in_modules:
                continue

            # First, expand any shorthand ranges specified in the config
            expanded_modules = self._expand_module_ranges(meta.due_in_modules)
            type_dates = self._generate_assessment_dates(
                assess_type, meta, base_start, base_end, exdates
            )

            # Map the parsed modules to their calculated schedules
            for mod_val in expanded_modules:
                if mod_val == "f":
                    self._schedule_final_assessment(
                        assess_type, meta, final_start, final_end
                    )
                else:
                    self._schedule_standard_assessment(assess_type, mod_val, type_dates)

    def get_module(self, number: int | str) -> CourseModule | None:
        return self.modules.get(number)

    def __iter__(self) -> Iterator[CourseModule]:
        # Sort modules numerically, pushing "f" (finals) to the very end
        return iter(
            sorted(
                self.modules.values(),
                key=lambda m: float("inf") if m.number == "f" else m.number,
            )
        )


class Student:
    """Encapsulates individual student data and calculates their progress relative to the course."""

    def __init__(self, full_name: str, orig_email: str, config: AppConfig) -> None:
        self.config: AppConfig = config
        self.full_name: str = full_name
        self.last_name, self.first_name = full_name.split(", ")

        # Ignore the original Canvas domain and use the one from config.toml
        username, _ = orig_email.split("@")
        self.email: str = f"{username}@{self.config.domain}"

        self.missing_assignments: list[str] = []

    def add_missing_assignment(self, assignment_desc: str) -> None:
        self.missing_assignments.append(assignment_desc)

    def get_status(self, current_module: int) -> dict[str, str | int]:
        last_module: int = current_module
        no_work_done: int = 0
        nothing_late: int = 1 if not self.missing_assignments else 0

        for desc in self.missing_assignments:
            if any(non_acad in desc for non_acad in self.config.non_academic):
                continue
            nothing_late = 0
            parts: list[str] = desc.split(self.config.assign_code_delimiter)
            if len(parts) > self.config.assign_code_index:
                assign_code: str = parts[self.config.assign_code_index]
            else:
                continue

            assign_str: str = "".join(ch for ch in assign_code if ch.isdigit())
            try:
                assign = int(assign_str)
            except ValueError:
                continue

            if assign_code.startswith(self.config.first_assess_code):
                no_work_done = 1
            if assign < last_module:
                last_module = assign

        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "modules_behind": current_module - last_module,
            "last_module": last_module,
            "no_work_done": no_work_done,
            "nothing_late": nothing_late,
        }


class Cohort:
    """Manages Student objects, relies on the Course class, and generates reports."""

    def __init__(
        self,
        config: AppConfig,
        current_module: int,
        as_of_date_str: str,
        midterm_alert: int,
        term_year: int,
    ) -> None:
        self.config: AppConfig = config
        self.current_module: int = current_module
        self.as_of_date_str: str = as_of_date_str
        self.midterm_alert: int = midterm_alert
        self._students: dict[str, Student] = {}
        # Delegate module scheduling and aggregation to the Course class
        self.course: Course = Course(self.config, term_year)

    def __iter__(self) -> Iterator[Student]:
        return iter(self._students.values())

    def get_or_create_student(self, full_name: str, email: str) -> Student:
        if full_name not in self._students:
            self._students[full_name] = Student(full_name, email, self.config)
        return self._students[full_name]

    def load_grades(self, filepath: pathlib.Path) -> None:
        with filepath.open("r", encoding="utf-8") as f:
            # Manually extract headers and skip the next two rows (e.g. Points Possible and Test Student)
            reader: Any = csv.reader(f)
            try:
                header = next(reader)
                next(reader)
                next(reader)
            except StopIteration:
                return

            dict_reader = csv.DictReader(f, fieldnames=header)
            for row in dict_reader:
                # csv.DictReader auto skips empty rows in standard cases, but keep check for safety
                if not row:
                    continue

                student_name = row.get(self.config.grades_student_col)
                email = row.get(self.config.grades_email_col)

                if not student_name or not email:
                    continue

                if any(
                    ignored in student_name for ignored in self.config.ignored_students
                ):
                    continue

                self.get_or_create_student(student_name, email)

    def load_missing_work(self, filepath: pathlib.Path) -> None:
        with filepath.open("r", encoding="utf-8") as f:
            dict_reader: Any = csv.DictReader(f)
            for row in dict_reader:
                if not row:
                    continue

                student_name = row.get(self.config.missing_student_col)
                assignment_desc = row.get(self.config.missing_assignment_col)

                if not student_name or not assignment_desc:
                    continue

                if student_name in self._students:
                    self._students[student_name].add_missing_assignment(assignment_desc)

    def _calculate_deadlines(self, today_date: datetime) -> dict[str, int | str]:
        deadlines: dict[str, int | str] = {}

        # Initialize dynamic deadline fields to -1 for any configured assessments
        for assess_type, meta in Assessment._type_registry.items():
            if meta.too_late_offset is not None:
                deadlines[f"{assess_type}_late"] = -1
                deadlines[f"{assess_type}_late_date"] = -1
            if meta.resubmission_offset is not None:
                deadlines[f"{assess_type}_resubmit"] = -1
                deadlines[f"{assess_type}_resubmit_date"] = -1

        # Iterate over aggregated CourseModules to dynamically query deadlines
        for mod in self.course:
            for assess_type, meta in Assessment._type_registry.items():
                assess = mod.get_assessment(assess_type)
                if not assess:
                    continue

                # Check too late offsets
                if meta.too_late_offset is not None and assess.too_late_date:
                    if (
                        today_date < assess.too_late_date
                        and deadlines[f"{assess_type}_late"] == -1
                    ):
                        deadlines[f"{assess_type}_late"] = mod.number
                        deadlines[f"{assess_type}_late_date"] = (
                            assess.too_late_date.strftime(self.config.date_format)
                        )

                # Check resubmission offsets
                if meta.resubmission_offset is not None and assess.resubmission_date:
                    if (
                        today_date < assess.resubmission_date
                        and deadlines[f"{assess_type}_resubmit"] == -1
                    ):
                        deadlines[f"{assess_type}_resubmit"] = mod.number
                        deadlines[f"{assess_type}_resubmit_date"] = (
                            assess.resubmission_date.strftime(self.config.date_format)
                        )

        return deadlines

    def generate_report(self, output_path: pathlib.Path, today_date: datetime) -> None:
        deadlines: dict[str, int | str] = self._calculate_deadlines(today_date)

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer: Any = csv.writer(f)
            writer.writerow(self.config.headers)

            for student in self:
                status: dict[str, str | int] = student.get_status(self.current_module)
                row: list[str | int] = [
                    self.config.active_number,
                    cast(str, status["first_name"]),
                    cast(str, status["last_name"]),
                    cast(str, status["email"]),
                    self.as_of_date_str,
                    self.midterm_alert,
                    cast(int, status["modules_behind"]),
                    cast(int, status["last_module"]),
                    self.current_module,
                    cast(int, status["no_work_done"]),
                    cast(int, status["nothing_late"]),
                ]

                # Dynamically append columns based on the active assessment rules
                for assess_type, meta in Assessment._type_registry.items():
                    if meta.too_late_offset is not None:
                        row.append(cast(int | str, deadlines[f"{assess_type}_late"]))
                        row.append(cast(str, deadlines[f"{assess_type}_late_date"]))
                    if meta.resubmission_offset is not None:
                        row.append(
                            cast(int | str, deadlines[f"{assess_type}_resubmit"])
                        )
                        row.append(cast(str, deadlines[f"{assess_type}_resubmit_date"]))

                writer.writerow(row)


def do_init(
    base_path_arg: str, courses: list[tuple[str, str]], force: bool = False
) -> None:
    """Handles the --init bootstrapping process."""
    # Resolve absolute path for base_path
    base_path_obj = pathlib.Path(base_path_arg)
    if not base_path_obj.is_absolute():
        base_path_obj = pathlib.Path.home() / base_path_obj
    base_path_str = str(base_path_obj).replace(
        "\\", "\\\\"
    )  # Escape for TOML if windows

    config_dir = get_config_home() / "courseStatus"
    config_dir.mkdir(parents=True, exist_ok=True)
    global_config_path = config_dir / "config.toml"

    prefixes = [c[0].upper() for c in courses]
    numbers = [int(c[1]) for c in courses]

    # If all prefixes are the same, collapse to a single string value for cleanliness
    if len(set(prefixes)) == 1:
        prefix_val = json.dumps(prefixes[0])
    else:
        prefix_val = json.dumps(prefixes)

    numbers_val = json.dumps(numbers)

    # Write global config if it doesn't exist, or if force is True
    if not global_config_path.exists() or force:
        if force and global_config_path.exists():
            logger.warning(
                f"Overwriting existing global configuration at {global_config_path} due to --force flag."
            )

        rendered_toml = DEFAULT_CONFIG_TEMPLATE.format(
            prefix_val=prefix_val,
            numbers_val=numbers_val,
            base_path_val=json.dumps(base_path_str),
        )
        global_config_path.write_text(rendered_toml, encoding="utf-8")
        logger.info(f"Initialized global configuration at: {global_config_path}")
    else:
        logger.warning(
            f"Global configuration already exists at {global_config_path}. Not overwriting."
        )

    # Create local directories and skeletons (unaffected by --force flag)
    for p, n in zip(prefixes, numbers):
        course_dir = base_path_obj / f"{p.lower()}{n}"
        course_dir.mkdir(parents=True, exist_ok=True)
        local_config_path = course_dir / "config.toml"

        if not local_config_path.exists():
            local_config_path.write_text(LOCAL_CONFIG_SKELETON, encoding="utf-8")
            logger.info(
                f"Created local course override skeleton at: {local_config_path}"
            )
        else:
            logger.info(f"Local config already exists at: {local_config_path}")

    logger.info("Initialization complete. You can now use the script normally.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process course statuses from Canvas grade files."
    )

    # Restructured arguments to remove required=True and add initialization logic
    parser.add_argument(
        "--init",
        type=str,
        metavar="BASE_PATH",
        help="Initialize configuration and directories",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite of the global config file (only valid with --init)",
    )
    parser.add_argument(
        "-c",
        "--course",
        nargs=2,
        action="append",
        metavar=("PREFIX", "NUMBER"),
        help="Course prefix and number",
    )
    parser.add_argument("-m", "--module", type=int, help="Current module number")
    parser.add_argument("-d", "--date", type=str, help="Date in MM-DD format")
    parser.add_argument(
        "--midterm", action="store_true", help="Flag to indicate midterm alert"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # If executed with no arguments, print the help text and exit gracefully
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose debug logging enabled.")

    # Ensure --force is only used alongside --init
    if args.force and not args.init:
        logger.error("The --force flag can only be used in conjunction with --init.")
        sys.exit(1)

    # Route execution to INIT phase if flag is present
    if args.init:
        if not args.course:
            logger.error(
                "Must provide at least one --course (-c <PREFIX> <NUMBER>) when running --init."
            )
            sys.exit(1)
        do_init(args.init, args.course, args.force)
        sys.exit(0)

    # Regular script execution validations
    if not args.course or len(args.course) != 1:
        logger.error(
            "Standard execution requires exactly one --course (-c <PREFIX> <NUMBER>)."
        )
        sys.exit(1)

    if not args.module:
        logger.error("Standard execution requires --module (-m).")
        sys.exit(1)

    req_prefix, req_number = args.course[0]
    config: AppConfig = AppConfig(req_prefix, req_number)

    today_date: datetime = datetime.now()
    month_day_str: str = args.date if args.date else today_date.strftime("%m-%d")

    try:
        as_of_date = datetime.strptime(f"{month_day_str}-{today_date.year}", "%m-%d-%Y")
    except ValueError:
        logger.error("Invalid date format. Must be MM-DD.")
        sys.exit(1)

    midterm_alert: int = 1 if args.midterm else 0

    base_path = (
        config.base_path_obj / f"{config.active_prefix.lower()}{config.active_number}"
    )
    if not base_path.exists():
        logger.error(f"Course directory '{base_path}' does not exist.")
        sys.exit(1)

    grades_file: pathlib.Path | None = None
    missing_file: pathlib.Path | None = None

    target_year_str = str(today_date.year)
    missing_pattern = re.compile(
        rf"^{config.missing_keyword}[ -]\d{{1,2}}-\d{{1,2}}-{target_year_str}\.csv$",
        re.IGNORECASE,
    )

    for file_path in base_path.glob(f"*{month_day_str}-{target_year_str}*.csv"):
        if config.grades_keyword in file_path.name:
            grades_file = file_path
        elif file_path.name.startswith(
            config.missing_keyword
        ) and missing_pattern.match(file_path.name):
            missing_file = file_path

    if not (grades_file and missing_file):
        logger.error(
            f"Missing grades or assignments files for date {month_day_str}-{target_year_str} in {base_path}."
        )
        sys.exit(1)

    safe_as_of_date: str = f"{as_of_date.month}/{as_of_date.day}/{as_of_date.year}"
    cohort: Cohort = Cohort(
        config, args.module, safe_as_of_date, midterm_alert, today_date.year
    )

    cohort.load_grades(grades_file)
    cohort.load_missing_work(missing_file)

    out_path: pathlib.Path = base_path / today_date.strftime(
        f"{config.output_prefix}%Y-%m-%d.csv"
    )
    cohort.generate_report(out_path, today_date)

    logger.info(f"Successfully generated report at: {out_path}")


if __name__ == "__main__":
    main()
