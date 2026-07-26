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
        too_late_offset: Optional[timedelta] = None,
        resubmission_offset: Optional[timedelta] = None,
    ) -> None:
        self.due_time: time = due_time
        self.due_day: str = due_day
        self.too_late_offset: Optional[timedelta] = too_late_offset
        self.resubmission_offset: Optional[timedelta] = resubmission_offset


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
        too_late_offset: Optional[timedelta] = None,
        resubmission_offset: Optional[timedelta] = None,
    ) -> None:
        """Registers the meta-information for a specific assessment type."""
        cls._type_registry[assess_type] = AssessmentMeta(
            due_time, due_day, too_late_offset, resubmission_offset
        )

    @classmethod
    def get_meta(cls, assess_type: str) -> Optional[AssessmentMeta]:
        return cls._type_registry.get(assess_type)

    def __init__(
        self, assess_type: str, due_date: datetime, strict_validation: bool = False
    ) -> None:
        self.type: str = assess_type
        self.due_date: datetime = due_date

        # Retrieve the meta-information for this specific assessment type
        meta: Optional[AssessmentMeta] = self._type_registry.get(self.type)
        if not meta:
            raise ValueError(
                f"Assessment type '{self.type}' is missing meta-configuration. Please register it first."
            )

        # Validate the schedule
        self._validate_schedule(meta, strict_validation)

        self.too_late_date: Optional[datetime] = None
        self.resubmission_date: Optional[datetime] = None

        # Calculate deadline attributes dynamically based on the
        # stored durations
        if meta.too_late_offset is not None:
            self.too_late_date = self.due_date + meta.too_late_offset

        if meta.resubmission_offset is not None:
            self.resubmission_date = self.due_date + meta.resubmission_offset

    def _validate_schedule(self, meta: AssessmentMeta, strict: bool) -> None:
        """Validates that the provided due_date aligns with the registered meta rules."""

        # Validate time
        if self.due_date.time() != meta.due_time:
            msg = f"{self.type} scheduled at {self.due_date.time()}, but expects {meta.due_time}."
            if strict:
                raise ValueError(msg)
            logger.debug(f"Schedule override: {msg}")

        # Validate Day of Week (strftime('%A') returns the full weekday name)
        actual_day = self.due_date.strftime("%A")
        if actual_day != meta.due_day:
            msg = f"{self.type} scheduled on {actual_day}, but expects {meta.due_day}."
            if strict:
                raise ValueError(msg)
            logger.debug(f"Schedule override: {msg}")

    def __repr__(self) -> str:
        return f"<Assessment(type='{self.type}', due_date={self.due_date.strftime('%Y-%m-%d %H:%M')})>"


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
        quizzes_data: Dict[str, Any] = assessment_data.get("Quizzes", {})
        assignments_data: Dict[str, Any] = assessment_data.get("Assignments", {})
        final_data: Dict[str, Any] = assessment_data.get("Final", {})
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

        # Base Dates
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

        # Parse and Register Assessment Configurations
        self._load_assessments(course_data.get("Assessments", {}))

    def _load_assessments(self, assessments_data: Dict[str, Any]) -> None:
        """Parses the nested assessment data and registers types into the Assessment class."""

        # Clear registry for clean state in testing environments
        Assessment._type_registry.clear()

        for assess_type, assess_config in assessments_data.items():
            if not isinstance(assess_config, dict):
                logger.warning(f"Skipping invalid assessment entry: '{assess_type}'")
                continue

            raw_time: Optional[str] = assess_config.get("due_time")
            due_day: Optional[str] = assess_config.get("due_day")

            if not raw_time or not due_day:
                logger.error(
                    f"Assessment '{assess_type}' is missing required 'due_time' or 'due_day' in config.toml."
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

            Assessment.register_type_meta(
                assess_type, parsed_time, due_day, too_late, resubmit
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

    def __init__(self, number: int) -> None:
        self.number: int = number
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
        self.modules: Dict[int, CourseModule] = {}
        self._initialize_modules()

    def _initialize_modules(self) -> None:
        start_m, start_d = map(int, self.config.raw_dates[0].split("-"))
        end_m, end_d = map(int, self.config.raw_dates[1].split("-"))

        # Build base term dates (times will be adjusted per assessment type)
        base_start: datetime = datetime(self.year, start_m, start_d)
        base_end: datetime = datetime(self.year, end_m, end_d)
        if base_end < base_start:
            base_end = base_end.replace(year=self.year + 1)

        # Parse exclusion dates
        exdates: List[datetime] = []
        for ex_str in self.config.raw_exclude_dates:
            ex_m, ex_d = map(int, ex_str.split("-"))
            ex_dt: datetime = datetime(self.year, ex_m, ex_d)
            if ex_dt < base_start and base_end.year > self.year:
                ex_dt = ex_dt.replace(year=self.year + 1)
            exdates.append(ex_dt)

        # Iterate over all registered assessment types to dynamically build schedules
        for assess_type, meta in Assessment._type_registry.items():
            due_day_const = DAY_MAP.get(meta.due_day, FR)

            type_start = base_start.replace(
                hour=meta.due_time.hour, minute=meta.due_time.minute
            )
            type_end = base_end.replace(
                hour=meta.due_time.hour, minute=meta.due_time.minute
            )

            rules: rruleset = rruleset()
            rules.rrule(
                rrule(
                    WEEKLY, byweekday=due_day_const, dtstart=type_start, until=type_end
                )
            )

            for ex_dt in exdates:
                # Align exclusion date with the assessment time
                rules.exdate(
                    ex_dt.replace(hour=meta.due_time.hour, minute=meta.due_time.minute)
                )

            type_dates: List[datetime] = list(rules)[: self.config.num_modules]

            # Populate Modules
            for i, dt in enumerate(type_dates, 1):
                if i not in self.modules:
                    self.modules[i] = CourseModule(i)
                self.modules[i].add_assessment(Assessment(assess_type, dt))

    def get_module(self, number: int) -> Optional[CourseModule]:
        return self.modules.get(number)

    def __iter__(self) -> Iterator[CourseModule]:
        return iter(sorted(self.modules.values(), key=lambda m: m.number))


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
                    cast(int, deadlines["quiz_late"]),
                    cast(str, deadlines["quiz_late_date"]),
                    cast(int, deadlines["assign_late"]),
                    cast(str, deadlines["assign_late_date"]),
                    cast(int, deadlines["resubmit"]),
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
