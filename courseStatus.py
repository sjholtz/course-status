#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

"""
Course Status Report Generator

This script processes Canvas gradebook exports and missing assignment reports
to generate a comprehensive CSV status report for students in a given course.
It operates via a command-line interface (CLI) and relies on a configuration
file (`config.ini`) for course-specific parameters, file paths, and output formatting.

Usage:
    python courseStatus.py -c <COURSE_NUM> -m <CURRENT_MODULE> [OPTIONS]

Example:
    python courseStatus.py -c 1151 -m 4 --date 02-15 --midterm

Dependencies:
    - Python 3.6+ (required for PEP 526 variable type annotations)
    - python-dateutil
    - config.ini file in the working directory
"""

import sys
import csv
import pathlib
import argparse
import configparser
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Iterator, Union, cast
from dateutil.rrule import MO, TU, WE, TH, FR, SA, SU, WEEKLY, rrule, rruleset

# Configure basic logging for the CLI application
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger: logging.Logger = logging.getLogger(__name__)

# Enforce Python 3.6+ to support modern variable type annotations
if sys.hexversion < 0x3060000:
    logger.critical("Must use python version 3.6 or greater.")
    sys.exit(1)

# Map string representations of weekdays from config.ini to dateutil constants
DAY_MAP: Dict[str, Any] = {
    "Monday": MO,
    "Tuesday": TU,
    "Wednesday": WE,
    "Thursday": TH,
    "Friday": FR,
    "Saturday": SA,
    "Sunday": SU,
}


class AppConfig:
    """
    Parses and stores settings from the configuration file (e.g., config.ini).

    Attributes:
        parser (ConfigParser): The configparser instance.
        prefix (str): Course prefix (e.g., 'CS').
        course_numbers (List[str]): List of valid course numbers.
        first_assess_code (str): The code signifying the first assessment.
        num_modules (int): Total number of modules in the course.
        non_academic (List[str]): List of non-academic assignments to ignore.
        raw_dates (List[str]): The Term Start and End Dates strings.
        raw_ex_dates (List[str]): Holiday and exclusion date strings.
        due_time_str (str): The string representing module due times (e.g., "5:00 PM").
        quiz_due_day (str): String representing the day quizzes are due.
        assign_due_day (str): String representing the day assignments are due.
        too_late_weeks (int): Number of weeks before an assignment is considered "too late".
        resubmit_weeks (int): Number of weeks before the resubmission deadline passes.
        base_path (str): The root directory where grade files are stored.
        headers (List[str]): CSV column headers for the output report.
        date_format (str): The string format for date representations.
    """

    def __init__(self, config_file: str = "config.ini") -> None:
        self.parser: configparser.ConfigParser = configparser.ConfigParser()
        if not self.parser.read(config_file):
            logger.error(f"Could not read config file '{config_file}'")
            sys.exit(1)

        # Parse [Course] section
        self.prefix: str = self.parser.get("Course", "Prefix", fallback="CS")
        self.course_numbers: List[str] = self.parser.get(
            "Course", "Numbers", fallback="1151 1411"
        ).split()
        self.first_assess_code: str = self.parser.get(
            "Course", "First Assess Code", fallback="Q1a"
        )
        self.num_modules: int = self.parser.getint(
            "Course", "Number of Modules", fallback=14
        )

        # Parse non-academic assessments into a list
        raw_non_academic: List[str] = (
            self.parser.get(
                "Course", "Non-Academic Assessments", fallback="Feedback Survey"
            )
            .strip()
            .split("\n")
        )
        self.non_academic: List[str] = [
            item.strip() for item in raw_non_academic if item.strip()
        ]

        # Dates and times for dynamic schedule generation
        self.raw_dates: List[str] = [
            d.strip()
            for d in self.parser.get("Course", "Dates", fallback="1-1\n12-31")
            .strip()
            .split("\n")
            if d.strip()
        ]
        self.raw_ex_dates: List[str] = [
            d.strip()
            for d in self.parser.get("Course", "Exclude Dates", fallback="")
            .strip()
            .split("\n")
            if d.strip()
        ]
        self.due_time_str: str = self.parser.get(
            "Course", "Due Time", fallback="5:00 PM"
        ).strip()
        self.quiz_due_day: str = self.parser.get(
            "Course", "Quiz Due Day", fallback="Friday"
        ).strip()
        self.assign_due_day: str = self.parser.get(
            "Course", "Assignment Due Day", fallback="Wednesday"
        ).strip()

        self.too_late_weeks: int = self.parser.getint(
            "Course", "Too Late Offset", fallback=2
        )
        self.resubmit_weeks: int = self.parser.getint(
            "Course", "Resubmission Deadline Offset", fallback=3
        )
        self.base_path: str = self.parser.get(
            "Course", "Base Path", fallback="~/Private/grades"
        )

        # Parse [Mail Merge] section
        raw_headers: List[str] = (
            self.parser.get("Mail Merge", "Headers", fallback="").strip().split("\n")
        )
        self.headers: List[str] = [h.strip() for h in raw_headers if h.strip()]
        self.date_format: str = self.parser.get(
            "Mail Merge", "Date Format", fallback="%-I:%M %p on %A %-d %B %Y"
        )


class CourseModule:
    """Represents a course module with specific due dates."""

    def __init__(
        self,
        number: int,
        quiz_date: Optional[datetime] = None,
        assignment_date: Optional[datetime] = None,
    ) -> None:
        self.number: int = number
        self.quiz_date: Optional[datetime] = quiz_date
        self.assignment_date: Optional[datetime] = assignment_date

    def __str__(self) -> str:
        return f"Module {self.number}"


class Student:
    """Encapsulates individual student data and calculates their progress relative to the course."""

    def __init__(self, full_name: str, orig_email: str, config: AppConfig) -> None:
        self.config: AppConfig = config
        self.full_name: str = full_name
        self.last_name: str
        self.first_name: str
        self.last_name, self.first_name = full_name.split(", ")

        username: str
        domain: str
        username, domain = orig_email.split("@")
        self.email: str = f"{username}@d.{domain}"
        self.missing_assignments: List[str] = []

    def add_missing_assignment(self, assignment_desc: str) -> None:
        self.missing_assignments.append(assignment_desc)

    def get_status(self, current_module: int) -> Dict[str, Union[str, int]]:
        last_module: int = current_module
        no_work_done: int = 0
        nothing_late: int = 1 if not self.missing_assignments else 0
        desc: str

        for desc in self.missing_assignments:
            if any(non_acad in desc for non_acad in self.config.non_academic):
                continue

            nothing_late = 0
            assign_code: str = desc.split()[1]
            assign_str: str = "".join(ch for ch in assign_code if ch.isdigit())

            assign: int
            try:
                assign = int(assign_str)
            except ValueError:
                continue

            if assign_code.startswith(self.config.first_assess_code):
                no_work_done = 1

            if assign < last_module:
                last_module = assign

        modules_behind: int = current_module - last_module

        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "modules_behind": modules_behind,
            "last_module": last_module,
            "no_work_done": no_work_done,
            "nothing_late": nothing_late,
        }

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} <{self.email}>"


class Cohort:
    """Manages a collection of Student objects, parses CSV files, and generates the final report."""

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

        self.too_late_offset: timedelta = timedelta(weeks=self.config.too_late_weeks)
        self.resubmission_offset: timedelta = timedelta(
            weeks=self.config.resubmit_weeks
        )

        self._students: Dict[str, Student] = {}
        self.modules: Dict[int, CourseModule] = self._initialize_modules(term_year)

    def _initialize_modules(self, term_year: int) -> Dict[int, CourseModule]:
        """
        Dynamically constructs the internal dictionary of modules and their strict due dates
        using python-dateutil's rrule based on config.ini term dates and exclusions.
        """
        due_time: datetime.time = datetime.strptime(
            self.config.due_time_str.upper(), "%I:%M %p"
        ).time()

        start_m: int
        start_d: int
        end_m: int
        end_d: int

        # Parse term start and end dates
        if len(self.config.raw_dates) >= 2:
            start_m, start_d = map(int, self.config.raw_dates[0].split("-"))
            end_m, end_d = map(int, self.config.raw_dates[1].split("-"))
        else:
            start_m, start_d = 1, 1
            end_m, end_d = 12, 31

        start_dt: datetime = datetime(
            term_year, start_m, start_d, due_time.hour, due_time.minute
        )
        end_dt: datetime = datetime(
            term_year, end_m, end_d, due_time.hour, due_time.minute
        )

        # Accommodate courses that cross into the new year
        if end_dt < start_dt:
            end_dt = end_dt.replace(year=term_year + 1)

        # Parse exclusion dates and assign exact times so rruleset.exdate() can match them
        exdates: List[datetime] = []
        ex_str: str
        for ex_str in self.config.raw_ex_dates:
            ex_m: int
            ex_d: int
            ex_m, ex_d = map(int, ex_str.split("-"))
            ex_dt: datetime = datetime(
                term_year, ex_m, ex_d, due_time.hour, due_time.minute
            )
            if ex_dt < start_dt and end_dt.year > term_year:
                ex_dt = ex_dt.replace(year=term_year + 1)
            exdates.append(ex_dt)

        # Convert strings ("Friday", "Wednesday") to dateutil constants (FR, WE)
        quiz_day: Any = DAY_MAP.get(self.config.quiz_due_day, FR)
        assign_day: Any = DAY_MAP.get(self.config.assign_due_day, WE)

        # Setup quiz recurring date rules
        quiz_rules: rruleset = rruleset()
        quiz_rules.rrule(
            rrule(WEEKLY, byweekday=quiz_day, dtstart=start_dt, until=end_dt)
        )
        for ex_dt in exdates:
            quiz_rules.exdate(ex_dt)

        # Setup assignment recurring date rules
        assign_rules: rruleset = rruleset()
        assign_rules.rrule(
            rrule(WEEKLY, byweekday=assign_day, dtstart=start_dt, until=end_dt)
        )
        for ex_dt in exdates:
            assign_rules.exdate(ex_dt)

        # Extract exactly N modules based on the config
        quiz_dates: List[datetime] = list(quiz_rules)[: self.config.num_modules]
        assign_dates: List[datetime] = list(assign_rules)[: self.config.num_modules]

        modules: Dict[int, CourseModule] = {}
        i: int
        q_date: datetime
        for i, q_date in enumerate(quiz_dates, 1):
            modules[i] = CourseModule(i, quiz_date=q_date)

        a_date: datetime
        for i, a_date in enumerate(assign_dates, 1):
            if i not in modules:
                modules[i] = CourseModule(i)
            modules[i].assignment_date = a_date

        return modules

    def __iter__(self) -> Iterator[Student]:
        return iter(self._students.values())

    def get_or_create_student(self, full_name: str, email: str) -> Student:
        if full_name not in self._students:
            self._students[full_name] = Student(full_name, email, self.config)
        return self._students[full_name]

    def load_grades(self, filepath: Union[str, pathlib.Path]) -> None:
        with open(filepath, "r") as f:
            reader: Any = csv.reader(f)
            next(reader)
            next(reader)
            row: List[str]
            for row in reader:
                name: str = row[0]
                if "Points Possible" in name or "Student, Test" in name:
                    continue
                self.get_or_create_student(name, row[3])

    def load_missing_work(self, filepath: Union[str, pathlib.Path]) -> None:
        with open(filepath, "r") as f:
            reader: Any = csv.reader(f)
            next(reader)
            missing_data: List[List[str]] = [row for row in reader]
            missing_data.sort(key=lambda x: x[0])

            row: List[str]
            for row in missing_data:
                name: str = row[0]
                if name in self._students:
                    self._students[name].add_missing_assignment(row[5])

    def _calculate_deadlines(self, today_date: datetime) -> Dict[str, Union[int, str]]:
        next_quiz_late: int = -1
        next_quiz_late_date: Union[int, str] = -1
        next_assign_late: int = -1
        next_assign_late_date: Union[int, str] = -1
        next_resubmit: int = -1
        next_resubmit_date: Union[int, str] = -1

        mod_num: int
        mod: CourseModule
        for mod_num, mod in sorted(self.modules.items()):
            if (
                mod.quiz_date
                and today_date < mod.quiz_date + self.too_late_offset
                and next_quiz_late == -1
            ):
                next_quiz_late = mod_num
                next_quiz_late_date = (mod.quiz_date + self.too_late_offset).strftime(
                    self.config.date_format
                )

            if mod.assignment_date:
                if (
                    today_date < mod.assignment_date + self.too_late_offset
                    and next_assign_late == -1
                ):
                    next_assign_late = mod_num
                    next_assign_late_date = (
                        mod.assignment_date + self.too_late_offset
                    ).strftime(self.config.date_format)

                if (
                    today_date < mod.assignment_date + self.resubmission_offset
                    and next_resubmit == -1
                ):
                    next_resubmit = mod_num
                    next_resubmit_date = (
                        mod.assignment_date + self.resubmission_offset
                    ).strftime(self.config.date_format)

        return {
            "quiz_late": next_quiz_late,
            "quiz_late_date": next_quiz_late_date,
            "assign_late": next_assign_late,
            "assign_late_date": next_assign_late_date,
            "resubmit": next_resubmit,
            "resubmit_date": next_resubmit_date,
        }

    def generate_report(self, output_path: pathlib.Path, today_date: datetime) -> None:
        deadlines: Dict[str, Union[int, str]] = self._calculate_deadlines(today_date)

        with open(output_path, "w", newline="") as f:
            writer: Any = csv.writer(f, dialect="unix")
            writer.writerow(self.config.headers)

            student: Student
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
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Process course statuses from Canvas grade files."
    )
    parser.add_argument(
        "-c",
        "--course",
        type=int,
        required=True,
        help="The course number (e.g., 1151, 1411).",
    )
    parser.add_argument(
        "-m",
        "--module",
        type=int,
        required=True,
        help="Current module students are working in (integer).",
    )
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        help="Month-day in missing assignments files (MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--midterm",
        action="store_true",
        help="Flag indicating if this run is for a midterm alert.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.ini",
        help="Path to configuration file. Defaults to config.ini.",
    )
    args: argparse.Namespace = parser.parse_args()

    config: AppConfig = AppConfig(args.config)

    if str(args.course) not in config.course_numbers:
        logger.error(
            f"Invalid course '{args.course}'. Expected one of {config.course_numbers}."
        )
        sys.exit(1)

    if not (1 <= args.module <= config.num_modules):
        logger.error(
            f"Invalid module '{args.module}'. Must be between 1 and {config.num_modules}."
        )
        sys.exit(1)

    today_date: datetime = datetime.now()
    month_day_str: str = args.date if args.date else today_date.strftime("%m-%d")

    as_of_date: datetime
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
        logger.error(f"Base path '{base_path}' does not exist or is not mounted!!!")
        sys.exit(1)

    grades_file: Optional[pathlib.Path] = None
    missing_file: Optional[pathlib.Path] = None

    file_path: pathlib.Path
    for file_path in base_path.iterdir():
        if month_day_str in file_path.name and file_path.suffix == ".csv":
            if "Grades" in file_path.name:
                grades_file = file_path
            elif file_path.name.startswith("missingAssignments"):
                missing_file = file_path

    if not (grades_file and missing_file):
        logger.error(
            f"Missing grades or assignments files for date {month_day_str} in {base_path}."
        )
        sys.exit(1)

    logger.info(f"Using grade data:              {grades_file}")
    logger.info(f"Using missing assignment data: {missing_file}")

    cohort: Cohort = Cohort(
        config,
        args.course,
        args.module,
        as_of_date.strftime("%-m/%-d/%Y"),
        midterm_alert,
        today_date.year,
    )
    cohort.load_grades(grades_file)
    cohort.load_missing_work(missing_file)

    out_path: pathlib.Path = base_path / today_date.strftime("status-%Y-%m-%d.csv")
    cohort.generate_report(out_path, today_date)

    logger.info(f"Successfully generated report at: {out_path}")
    logger.info("All Done! Have a great day!")


if __name__ == "__main__":
    main()
