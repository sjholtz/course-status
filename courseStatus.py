#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import sys
import csv
import pathlib
import argparse
import configparser
from datetime import datetime, timedelta

# Enforce Python Version
if sys.hexversion < 0x3050000:
    print("Must use python version 3.5 or greater.", file=sys.stderr)
    sys.exit(1)


class AppConfig:
    """Parses and stores settings from config.ini."""

    def __init__(self, config_file="config.ini"):
        self.parser = configparser.ConfigParser()
        if not self.parser.read(config_file):
            print(f"ERROR: Could not read config file '{config_file}'", file=sys.stderr)
            sys.exit(1)

        # [Course] settings
        self.prefix = self.parser.get("Course", "Prefix", fallback="CS")
        self.course_numbers = self.parser.get(
            "Course", "Numbers", fallback="1151 1411"
        ).split()
        self.first_assess_code = self.parser.get(
            "Course", "First Assess Code", fallback="Q1a"
        )
        self.num_modules = self.parser.getint(
            "Course", "Number of Modules", fallback=14
        )

        self.quiz_due_day = self.parser.get("Course", "Quiz Due Day", fallback="Friday")
        self.assign_due_day = self.parser.get(
            "Course", "Assignment Due Day", fallback="Wednesday"
        )

        self.too_late_weeks = self.parser.getint(
            "Course", "Too Late Offset", fallback=2
        )
        self.resubmit_weeks = self.parser.getint(
            "Course", "Resubmission Deadline Offset", fallback=3
        )
        self.base_path = self.parser.get(
            "Course", "Base Path", fallback="~/Private/grades"
        )

        # [Mail Merge] settings
        raw_headers = (
            self.parser.get("Mail Merge", "Headers", fallback="").strip().split("\n")
        )
        self.headers = [h.strip() for h in raw_headers if h.strip()]
        self.date_format = self.parser.get(
            "Mail Merge", "Date Format", fallback="%-I:%M %p on %A %-d %B %Y"
        )


class CourseModule:
    """Represents a module with its quiz and assignment due dates."""

    def __init__(self, number, quiz_date=None, assignment_date=None):
        self.number = number
        self.quiz_date = quiz_date
        self.assignment_date = assignment_date

    def __str__(self):
        return f"Module {self.number}"


class Student:
    """Encapsulates student data and calculates progress/status."""

    def __init__(self, full_name, orig_email, config):
        self.config = config
        self.full_name = full_name
        self.last_name, self.first_name = full_name.split(", ")

        username, domain = orig_email.split("@")
        self.email = f"{username}@d.{domain}"
        self.missing_assignments = []

    def add_missing_assignment(self, assignment_desc):
        self.missing_assignments.append(assignment_desc)

    def get_status(self, current_module):
        last_module = current_module
        no_work_done = 0
        nothing_late = 1 if not self.missing_assignments else 0

        for desc in self.missing_assignments:
            if "Feedback Survey" in desc:
                continue

            nothing_late = 0
            assign_code = desc.split()[1]

            assign_str = "".join(ch for ch in assign_code if ch.isdigit())
            try:
                assign = int(assign_str)
            except ValueError:
                continue

            if assign_code.startswith(self.config.first_assess_code):
                no_work_done = 1

            if assign < last_module:
                last_module = assign

        modules_behind = current_module - last_module

        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "modules_behind": modules_behind,
            "last_module": last_module,
            "no_work_done": no_work_done,
            "nothing_late": nothing_late,
        }

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}>"


class Cohort:
    """Manages a collection of students, dates, and handles I/O."""

    def __init__(
        self, config, course_num, current_module, as_of_date_str, midterm_alert
    ):
        self.config = config
        self.course_num = course_num
        self.current_module = current_module
        self.as_of_date_str = as_of_date_str
        self.midterm_alert = midterm_alert

        self.too_late_offset = timedelta(weeks=self.config.too_late_weeks)
        self.resubmission_offset = timedelta(weeks=self.config.resubmit_weeks)

        self._students = {}
        self.modules = self._initialize_modules()

    def _initialize_modules(self):
        modules = {}
        quiz_dates = [
            (1, datetime(2026, 1, 16, hour=17)),
            (2, datetime(2026, 1, 23, hour=17)),
            (3, datetime(2026, 1, 30, hour=17)),
            (4, datetime(2026, 2, 6, hour=17)),
            (5, datetime(2026, 2, 13, hour=17)),
            (6, datetime(2026, 2, 20, hour=17)),
            (7, datetime(2026, 2, 27, hour=17)),
            (8, datetime(2026, 3, 6, hour=17)),
            (9, datetime(2026, 3, 20, hour=17)),
            (10, datetime(2026, 3, 27, hour=17)),
            (11, datetime(2026, 4, 3, hour=17)),
            (12, datetime(2026, 4, 10, hour=17)),
            (13, datetime(2026, 4, 17, hour=17)),
        ]
        assignment_dates = [
            (1, datetime(2026, 1, 21, hour=17)),
            (2, datetime(2026, 1, 28, hour=17)),
            (3, datetime(2026, 2, 4, hour=17)),
            (4, datetime(2026, 2, 11, hour=17)),
            (5, datetime(2026, 2, 18, hour=17)),
            (6, datetime(2026, 2, 25, hour=17)),
            (7, datetime(2026, 3, 4, hour=17)),
            (8, datetime(2026, 3, 18, hour=17)),
            (9, datetime(2026, 3, 25, hour=17)),
            (10, datetime(2026, 4, 1, hour=17)),
            (11, datetime(2026, 4, 8, hour=17)),
            (12, datetime(2026, 4, 15, hour=17)),
            (13, datetime(2026, 4, 22, hour=17)),
            (14, datetime(2026, 5, 8, hour=17)),
        ]

        for q_num, q_date in quiz_dates:
            modules[q_num] = CourseModule(q_num, quiz_date=q_date)
        for a_num, a_date in assignment_dates:
            if a_num not in modules:
                modules[a_num] = CourseModule(a_num)
            modules[a_num].assignment_date = a_date

        return modules

    def __iter__(self):
        return iter(self._students.values())

    def get_or_create_student(self, full_name, email):
        if full_name not in self._students:
            self._students[full_name] = Student(full_name, email, self.config)
        return self._students[full_name]

    def load_grades(self, filepath):
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            next(reader)
            next(reader)
            for row in reader:
                name = row[0]
                if "Points Possible" in name or "Student, Test" in name:
                    continue
                self.get_or_create_student(name, row[3])

    def load_missing_work(self, filepath):
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            next(reader)
            missing_data = [row for row in reader if "S25" not in row[5]]
            missing_data.sort(key=lambda x: x[0])

            for row in missing_data:
                name = row[0]
                if name in self._students:
                    self._students[name].add_missing_assignment(row[5])

    def _calculate_deadlines(self, today_date):
        next_quiz_late = next_quiz_late_date = -1
        next_assign_late = next_assign_late_date = -1
        next_resubmit = next_resubmit_date = -1

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

    def generate_report(self, output_path, today_date):
        deadlines = self._calculate_deadlines(today_date)

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerow(self.config.headers)

            for student in self:
                status = student.get_status(self.current_module)
                row = [
                    self.course_num,
                    status["first_name"],
                    status["last_name"],
                    status["email"],
                    self.as_of_date_str,
                    self.midterm_alert,
                    status["modules_behind"],
                    status["last_module"],
                    self.current_module,
                    status["no_work_done"],
                    status["nothing_late"],
                    deadlines["quiz_late"],
                    deadlines["quiz_late_date"],
                    deadlines["assign_late"],
                    deadlines["assign_late_date"],
                    deadlines["resubmit"],
                    deadlines["resubmit_date"],
                ]
                writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
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
    args = parser.parse_args()

    config = AppConfig(args.config)

    # Validate inputs against configuration
    if str(args.course) not in config.course_numbers:
        print(
            f"ERROR: Invalid course '{args.course}'. Expected one of {config.course_numbers}.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not (1 <= args.module <= config.num_modules):
        print(
            f"ERROR: Invalid module '{args.module}'. Must be between 1 and {config.num_modules}.",
            file=sys.stderr,
        )
        sys.exit(1)

    today_date = datetime.now()
    month_day_str = args.date if args.date else today_date.strftime("%m-%d")

    try:
        as_of_date = datetime.strptime(f"{month_day_str}-{today_date.year}", "%m-%d-%Y")
    except ValueError:
        print("ERROR: Invalid date format. Must be MM-DD.", file=sys.stderr)
        sys.exit(1)

    midterm_alert = 1 if args.midterm else 0

    # Setup file paths
    base_path = pathlib.Path(
        f"{config.base_path}/{config.prefix.lower()}{args.course}"
    ).expanduser()
    if not base_path.exists():
        print(
            f"ERROR: Base path '{base_path}' does not exist or is not mounted!!!",
            file=sys.stderr,
        )
        sys.exit(1)

    grades_file = missing_file = None
    for file_path in base_path.iterdir():
        if month_day_str in file_path.name and file_path.suffix == ".csv":
            if "Grades" in file_path.name:
                grades_file = file_path
            elif file_path.name.startswith("missingAssignments"):
                missing_file = file_path

    if not (grades_file and missing_file):
        print(
            f"ERROR: Missing grades or assignments files for date {month_day_str} in {base_path}.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Using grade data:              {grades_file}")
    print(f"Using missing assignment data: {missing_file}")

    cohort = Cohort(
        config,
        args.course,
        args.module,
        as_of_date.strftime("%-m/%-d/%Y"),
        midterm_alert,
    )
    cohort.load_grades(grades_file)
    cohort.load_missing_work(missing_file)

    out_path = base_path / today_date.strftime("status-%Y-%m-%d.csv")
    cohort.generate_report(out_path, today_date)

    print(f"Successfully generated report at: {out_path}")
    print("All Done! Have a great day!")


if __name__ == "__main__":
    main()
