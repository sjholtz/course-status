#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

"""
Course Status Report Generator

This script processes Canvas gradebook exports and missing assignment reports
to generate a comprehensive CSV status report for students in a given course.
It operates via a command-line interface (CLI) and relies on a configuration
file (`config.toml`) for course-specific parameters, file paths, and output formatting.

Usage:
    python courseStatus.py -c <COURSE_NUM> -m <CURRENT_MODULE> [OPTIONS]

Example:
    python courseStatus.py -c 1151 -m 4 --date 02-15 --midterm -v

Dependencies:
    - Python 3.11+ (required for standard library tomllib)
    - python-dateutil
    - config.toml file in the working directory
"""

import os
import sys
import csv
import re
import pathlib
import argparse
import logging
import tomllib
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Any, Iterator, Union, cast
from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU, WEEKLY, rrule, rruleset

# Configure basic logging for the CLI application
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

# Enforce Python 3.11+ to support native tomllib
if sys.hexversion < 0x030B0000:
    logger.critical("Must use Python version 3.11 or greater for TOML support.")
    sys.exit(1)

# Map string representations of weekdays from config.toml to dateutil constants
DAY_MAP: Dict[str, Any] = {
    "Monday": MO,
    "Tuesday": TU,
    "Wednesday": WE,
    "Thursday": TH,
    "Friday": FR,
    "Saturday": SA,
    "Sunday": SU,
}


class AssessmentMeta:
    """Stores the definitive configuration and rules for a specific assessment type."""

    def __init__(
        self,
        due_time: time,
        due_day: str,
        due_in_modules: List[str],
        too_late_offset: Optional[timedelta] = None,
        resubmission_offset: Optional[timedelta] = None,
        final_due_time: Optional[time] = None,
        final_due_day: Optional[str] = None,
    ) -> None:
        self.due_time: time = due_time
        self.due_day: str = due_day
        self.due_in_modules: List[str] = due_in_modules
        self.too_late_offset: Optional[timedelta] = too_late_offset
        self.resubmission_offset: Optional[timedelta] = resubmission_offset
        self.final_due_time: Optional[time] = final_due_time
        self.final_due_day: Optional[str] = final_due_day


class Assessment:
    """Represents an individual assessment that counts toward a student's grade."""

    # Class-level registry acting as the meta-class storage for each assessment 'type'
    _type_registry: Dict[str, AssessmentMeta] = {}

    @classmethod
    def register_type_meta(
        cls,
        assess_type: str,
        due_time: time,
        due_day: str,
        due_in_modules: List[str],
        too_late_offset: Optional[timedelta] = None,
        resubmission_offset: Optional[timedelta] = None,
        final_due_time: Optional[time] = None,
        final_due_day: Optional[str] = None,
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
        )

    @classmethod
    def get_meta(cls, assess_type: str) -> Optional[AssessmentMeta]:
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
        meta: Optional[AssessmentMeta] = self._type_registry.get(self.type)
        if not meta:
            raise ValueError(
                f"Assessment type '{self.type}' is missing meta-configuration. Please register it first."
            )

        # Validate the schedule
        self._validate_schedule(meta, strict_validation, self.is_final)

        self.too_late_date: Optional[datetime] = None
        self.resubmission_date: Optional[datetime] = None

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
    """Parses and stores settings from the configuration file."""

    def __init__(self, config_file: str = "config.toml") -> None:
        config_path: pathlib.Path = pathlib.Path(config_file)

        if not config_path.is_file():
            logger.error(f"Could not read config file '{config_file}'")
            sys.exit(1)

        # Parse the TOML file natively into a dictionary
        config_content: str = config_path.read_text(encoding="utf-8")
        try:
            config_data: Dict[str, Any] = tomllib.loads(config_content)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error parsing TOML config: {e}")
            sys.exit(1)

        course_data: Dict[str, Any] = config_data.get("Course", {})
        dates_data: Dict[str, Any] = course_data.get("Dates", {})
        assessment_data: Dict[str, Any] = course_data.get("Assessments", {})
        system_data: Dict[str, Any] = config_data.get("System", {})
        mail_merge_data: Dict[str, Any] = config_data.get("Mail_Merge", {})

        # Load [Course] variables natively, providing fallbacks
        self.prefix: str = course_data.get("prefix", "CS")

        # Convert the integer array to strings for CLI matching
        raw_numbers: List[int] = course_data.get("numbers", [1151, 1411])
        self.course_numbers: List[str] = [str(num) for num in raw_numbers]

        self.first_assess_code: str = course_data.get("first_assess_code", "Q1a")

        self.num_modules: int = course_data.get("number_of_modules", 14)
        self.non_academic: List[str] = assessment_data.get(
            "non_academic_assessments", ["Feedback Survey"]
        )
        self.ignored_students: List[str] = course_data.get(
            "ignored_students", ["Points Possible", "Student, Test"]
        )

        # Base dates
        self.raw_dates: List[str] = dates_data.get("dates", ["1-1", "12-31"])
        self.raw_exclude_dates: List[str] = dates_data.get("exclude_dates", [])
        self.raw_final_dates: List[str] = dates_data.get("final_dates", [])

        # Validate the dates extracted from the config
        self._validate_dates()

        self.base_path: str = course_data.get("base_path", "~/Private/grades")

        # Load [System] variables natively
        self.grades_keyword: str = system_data.get("grades_file_keyword", "Grades")
        self.missing_keyword: str = system_data.get(
            "missing_file_keyword", "missingAssignments"
        )
        self.output_prefix: str = system_data.get("output_file_prefix", "status-")
        self.assign_code_index: int = system_data.get("assignment_code_index", 1)
        raw_delimiter: str = system_data.get("assignment_code_delimiter", " ")
        # Map a single space to None so Python's split() handles consecutive whitespace safely
        self.assign_code_delimiter: Optional[str] = (
            None if raw_delimiter == " " else raw_delimiter
        )

        # Load [Mail_Merge] variables natively
        self.headers: List[str] = mail_merge_data.get(
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
        self._load_assessments(course_data.get("Assessments", {}))

    def _load_assessments(self, assessments_data: Dict[str, Any]) -> None:
        """Parses the nested assessment data and registers types into the Assessment class."""

        # Clear registry for clean state in testing environments
        Assessment._type_registry.clear()

        for assess_type, assess_config in assessments_data.items():
            if not isinstance(assess_config, dict):
                continue

            raw_time: Optional[str] = assess_config.get("due_time")
            due_day: Optional[str] = assess_config.get("due_day")
            due_in_modules: Optional[List[str]] = assess_config.get("due_in_modules")

            if raw_time is None or due_day is None or due_in_modules is None:
                logger.error(
                    f"Assessment '{assess_type}' is missing required 'due_time', 'due_day', or 'due_in_modules'."
                )
                sys.exit(1)

            parsed_time: time = datetime.strptime(raw_time.upper(), "%I:%M %p").time()

            tl_offset: Optional[int] = assess_config.get("too_late_deadline_offset")
            rs_offset: Optional[int] = assess_config.get("resubmission_deadline_offset")

            too_late: Optional[timedelta] = (
                timedelta(days=tl_offset) if tl_offset is not None else None
            )
            resubmit: Optional[timedelta] = (
                timedelta(days=rs_offset) if rs_offset is not None else None
            )

            final_due_time_raw: Optional[str] = assess_config.get("final_due_time")
            final_due_day: Optional[str] = assess_config.get("final_due_day")
            final_due_time: Optional[time] = (
                datetime.strptime(final_due_time_raw.upper(), "%I:%M %p").time()
                if final_due_time_raw
                else None
            )

            Assessment.register_type_meta(
                assess_type,
                parsed_time,
                due_day,
                due_in_modules,
                too_late,
                resubmit,
                final_due_time,
                final_due_day,
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

        for d_str in self.raw_dates:
            check_date(d_str)
        for d_str in self.raw_final_dates:
            check_date(d_str)
        for d_str in self.raw_exclude_dates:
            check_date(d_str)


class CourseModule:
    """Holds a singular module and its associated assessments."""

    def __init__(self, number: Union[int, str]) -> None:
        self.number: Union[int, str] = number
        self.assessments: Dict[str, Assessment] = {}

    def add_assessment(self, assess: Assessment) -> None:
        self.assessments[assess.type] = assess

    def get_assessment(self, assess_type: str) -> Optional[Assessment]:
        return self.assessments.get(assess_type)

    def __str__(self) -> str:
        return f"Module {self.number} ({len(self.assessments)} assessments)"


class Course:
    """Aggregates CourseModule objects and supports module lookup and iteration."""

    def __init__(self, config: AppConfig, year: int) -> None:
        self.config: AppConfig = config
        self.year: int = year
        self.modules: Dict[Union[int, str], CourseModule] = {}
        self._initialize_modules()

    def _parse_term_dates(self) -> tuple[datetime, datetime]:
        """Parses and calculates the base term start and end dates[cite: 2]."""
        start_m, start_d = map(int, self.config.raw_dates[0].split("-"))
        end_m, end_d = map(int, self.config.raw_dates[1].split("-"))

        base_start: datetime = datetime(self.year, start_m, start_d)
        base_end: datetime = datetime(self.year, end_m, end_d)

        if base_end < base_start:
            base_end = base_end.replace(year=self.year + 1)

        return base_start, base_end

    def _parse_finals_dates(self, base_start: datetime) -> tuple[datetime, datetime]:
        """Parses and calculates the finals week start and end dates[cite: 2]."""
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

    def _parse_exclusion_dates(self, base_start: datetime, base_end: datetime) -> List[datetime]:
        """Parses individual exclusion dates and handles term wrapping[cite: 2]."""
        exdates: List[datetime] = []
        for ex_str in self.config.raw_exclude_dates:
            ex_m, ex_d = map(int, ex_str.split("-"))
            ex_dt: datetime = datetime(self.year, ex_m, ex_d)
            if ex_dt < base_start and base_end.year > self.year:
                ex_dt = ex_dt.replace(year=self.year + 1)
            exdates.append(ex_dt)
        return exdates

    def _expand_module_ranges(self, due_in_modules: List[str]) -> List[str]:
        """Expands shorthand configuration ranges (e.g., '1-14', '-3', '13-') into explicit string identifiers[cite: 4]."""
        expanded: List[str] = []

        for mod_val in due_in_modules:
            mod_val = mod_val.strip().lower()

            if mod_val == "f":
                expanded.append("f")
            elif "-" in mod_val:
                parts = mod_val.split("-")
                start_str = parts[0].strip()
                end_str = parts[1].strip() if len(parts) > 1 else ""

                try:
                    # Default to 1 if no start is provided (e.g., "-3")[cite: 4]
                    start = int(start_str) if start_str else 1
                    # Default to total modules if no end is provided (e.g., "13-")[cite: 4]
                    end = int(end_str) if end_str else self.config.num_modules

                    for i in range(start, end + 1):
                        expanded.append(str(i))
                except ValueError:
                    logger.warning(f"Invalid module range format '{mod_val}'. Skipping.")
            else:
                expanded.append(mod_val)

        return expanded

    def _generate_assessment_dates(self, meta: AssessmentMeta, start: datetime, end: datetime, exdates: List[datetime]) -> List[datetime]:
        """Generates the standard weekly recurrence rules for the regular term[cite: 2]."""
        due_day_const = DAY_MAP.get(meta.due_day, FR)
        type_start = start.replace(hour=meta.due_time.hour, minute=meta.due_time.minute)
        type_end = end.replace(hour=meta.due_time.hour, minute=meta.due_time.minute)

        rules: rruleset = rruleset()
        rules.rrule(
            rrule(WEEKLY, byweekday=due_day_const, dtstart=type_start, until=type_end)
        )

        for ex_dt in exdates:
            rules.exdate(ex_dt.replace(hour=meta.due_time.hour, minute=meta.due_time.minute))

        return list(rules)[: self.config.num_modules]

    def _schedule_final_assessment(self, assess_type: str, meta: AssessmentMeta, final_start: datetime, final_end: datetime) -> None:
        """Determines the specific final week date and assigns it to the 'f' module[cite: 2]."""
        if not meta.final_due_day or not meta.final_due_time:
            logger.error(f"Assessment '{assess_type}' specifies 'f' but is missing final_due_day or final_due_time.")
            sys.exit(1)

        final_day_const = DAY_MAP.get(meta.final_due_day, FR)
        f_start = final_start.replace(hour=meta.final_due_time.hour, minute=meta.final_due_time.minute)
        f_end = final_end.replace(hour=meta.final_due_time.hour, minute=meta.final_due_time.minute)

        f_rules = rrule(WEEKLY, byweekday=final_day_const, dtstart=f_start, until=f_end)
        f_dates = list(f_rules)

        if not f_dates:
            logger.error(f"Could not find a {meta.final_due_day} during finals week for {assess_type}.")
            sys.exit(1)

        f_dt = f_dates[0]

        if "f" not in self.modules:
            self.modules["f"] = CourseModule("f")
        self.modules["f"].add_assessment(Assessment(assess_type, f_dt, is_final=True))

    def _schedule_standard_assessment(self, assess_type: str, mod_val: str, type_dates: List[datetime]) -> None:
        """Matches a standard assessment with its corresponding date and assigns it to a numbered module[cite: 2]."""
        try:
            mod_int = int(mod_val)
        except ValueError:
            logger.warning(f"Invalid module identifier '{mod_val}' in {assess_type} config. Skipping.")
            return

        if 1 <= mod_int <= len(type_dates):
            if mod_int not in self.modules:
                self.modules[mod_int] = CourseModule(mod_int)
            self.modules[mod_int].add_assessment(Assessment(assess_type, type_dates[mod_int - 1]))

    def _initialize_modules(self) -> None:
        """Coordinates the initialization of all modules and their respective assessments[cite: 2]."""
        base_start, base_end = self._parse_term_dates()
        final_start, final_end = self._parse_finals_dates(base_start)
        exdates = self._parse_exclusion_dates(base_start, base_end)

        for assess_type, meta in Assessment._type_registry.items():
            if not meta.due_in_modules:
                continue

            # First, expand any shorthand ranges specified in the config[cite: 4]
            expanded_modules = self._expand_module_ranges(meta.due_in_modules)
            type_dates = self._generate_assessment_dates(meta, base_start, base_end, exdates)

            # Map the parsed modules to their calculated schedules
            for mod_val in expanded_modules:
                if mod_val == "f":
                    self._schedule_final_assessment(assess_type, meta, final_start, final_end)
                else:
                    self._schedule_standard_assessment(assess_type, mod_val, type_dates)

    def get_module(self, number: Union[int, str]) -> Optional[CourseModule]:
        return self.modules.get(number)

    def __iter__(self) -> Iterator[CourseModule]:
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

        self.missing_assignments: List[str] = []

    def add_missing_assignment(self, assignment_desc: str) -> None:
        self.missing_assignments.append(assignment_desc)

    def get_status(self, current_module: int) -> Dict[str, Union[str, int]]:
        last_module: int = current_module
        no_work_done: int = 0
        nothing_late: int = 1 if not self.missing_assignments else 0

        for desc in self.missing_assignments:
            if any(non_acad in desc for non_acad in self.config.non_academic):
                continue
            nothing_late = 0
            parts: List[str] = desc.split(self.config.assign_code_delimiter)
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
        course_num: int,
        current_module: int,
        as_of_date_str: str,
        midterm_alert: int,
        term_year: int,
    ) -> None:
        self.config: AppConfig = config
        self.course_num: int = course_num
        self.current_module: int = current_module
        self.as_of_date_str: str = as_of_date_str
        self.midterm_alert: int = midterm_alert

        self._students: Dict[str, Student] = {}
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
            reader: Any = csv.reader(f)
            next(reader)
            next(reader)
            for row in reader:
                if not row:
                    continue
                if any(ignored in row[0] for ignored in self.config.ignored_students):
                    continue
                self.get_or_create_student(row[0], row[3])

    def load_missing_work(self, filepath: pathlib.Path) -> None:
        with filepath.open("r", encoding="utf-8") as f:
            reader: Any = csv.reader(f)
            next(reader)
            missing_data: List[List[str]] = [row for row in reader if row]
            for row in missing_data:
                if row[0] in self._students:
                    self._students[row[0]].add_missing_assignment(row[5])

    def _calculate_deadlines(self, today_date: datetime) -> Dict[str, Union[int, str]]:
        deadlines: Dict[str, Union[int, str]] = {
            "quiz_late": -1,
            "quiz_late_date": -1,
            "assign_late": -1,
            "assign_late_date": -1,
            "resubmit": -1,
            "resubmit_date": -1,
        }

        # Iterate over aggregated CourseModules to dynamically query deadlines
        for mod in self.course:
            quiz = mod.get_assessment("Quiz")
            if (
                quiz
                and quiz.too_late_date
                and today_date < quiz.too_late_date
                and deadlines["quiz_late"] == -1
            ):
                deadlines["quiz_late"] = mod.number
                deadlines["quiz_late_date"] = quiz.too_late_date.strftime(
                    self.config.date_format
                )

            assign = mod.get_assessment("Assignment")
            if assign:
                if (
                    assign.too_late_date
                    and today_date < assign.too_late_date
                    and deadlines["assign_late"] == -1
                ):
                    deadlines["assign_late"] = mod.number
                    deadlines["assign_late_date"] = assign.too_late_date.strftime(
                        self.config.date_format
                    )

                if (
                    assign.resubmission_date
                    and today_date < assign.resubmission_date
                    and deadlines["resubmit"] == -1
                ):
                    deadlines["resubmit"] = mod.number
                    deadlines["resubmit_date"] = assign.resubmission_date.strftime(
                        self.config.date_format
                    )

        return deadlines

    def generate_report(self, output_path: pathlib.Path, today_date: datetime) -> None:
        deadlines: Dict[str, Union[int, str]] = self._calculate_deadlines(today_date)

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer: Any = csv.writer(f)
            writer.writerow(self.config.headers)

            for student in self:
                status: Dict[str, Union[str, int]] = student.get_status(
                    self.current_module
                )
                row: List[Union[str, int]] = [
                    self.course_num,
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
                    cast(Union[int, str], deadlines["quiz_late"]),
                    cast(str, deadlines["quiz_late_date"]),
                    cast(Union[int, str], deadlines["assign_late"]),
                    cast(str, deadlines["assign_late_date"]),
                    cast(Union[int, str], deadlines["resubmit"]),
                    cast(str, deadlines["resubmit_date"]),
                ]
                writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process course statuses from Canvas grade files."
    )
    parser.add_argument("-c", "--course", type=int, required=True)
    parser.add_argument("-m", "--module", type=int, required=True)
    parser.add_argument("-d", "--date", type=str)
    parser.add_argument("--midterm", action="store_true")
    parser.add_argument("--config", type=str, default="config.toml")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose debug logging enabled.")

    config: AppConfig = AppConfig(args.config)

    if str(args.course) not in config.course_numbers:
        logger.error(
            f"Invalid course '{args.course}'. Expected one of {config.course_numbers}."
        )
        sys.exit(1)

    today_date: datetime = datetime.now()
    month_day_str: str = args.date if args.date else today_date.strftime("%m-%d")

    try:
        as_of_date = datetime.strptime(f"{month_day_str}-{today_date.year}", "%m-%d-%Y")
    except ValueError:
        logger.error("Invalid date format. Must be MM-DD.")
        sys.exit(1)

    midterm_alert: int = 1 if args.midterm else 0

    base_path: pathlib.Path = pathlib.Path(
        f"{config.base_path}/{config.prefix.lower()}{args.course}"
    ).expanduser()
    if not base_path.exists():
        logger.error(f"Base path '{base_path}' does not exist.")
        sys.exit(1)

    grades_file: Optional[pathlib.Path] = None
    missing_file: Optional[pathlib.Path] = None

    pattern = re.compile(
        rf"^{config.missing_keyword}[ -]\d{{1,2}}-\d{{1,2}}-\d{{4}}\.csv$",
        re.IGNORECASE,
    )
    for file_path in base_path.iterdir():
        if month_day_str in file_path.name and file_path.suffix == ".csv":
            if config.grades_keyword in file_path.name:
                grades_file = file_path
            elif file_path.name.startswith(config.missing_keyword) and pattern.match(
                file_path.name
            ):
                missing_file = file_path

    if not (grades_file and missing_file):
        logger.error(
            f"Missing grades or assignments files for date {month_day_str} in {base_path}."
        )
        sys.exit(1)

    safe_as_of_date: str = f"{as_of_date.month}/{as_of_date.day}/{as_of_date.year}"
    cohort: Cohort = Cohort(
        config,
        args.course,
        args.module,
        safe_as_of_date,
        midterm_alert,
        today_date.year,
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
