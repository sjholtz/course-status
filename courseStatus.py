#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

"""courseStatus.py

Processes the most recent Canvas LMS gradebook and missing assignments
report CSV files into a CSV file used as input to the Thunderbird Mail
Merge add on. (https://addons.thunderbird.net/addon/mail-merge/).

DEPENDENCIES:
 - Standard Libraries: sys, csv, argparse, datetime, operator,
                       pathlib, configparser
 - Third-Party Packages: dateutil

USAGE EXAMPLES:
  # Run with all defaults (Course index 0, current week module, today's date)
  $ python3 courseStatus.py

  # Run for course 1411, module 5, specific date, and include midterm alert
  $ python3 courseStatus.py --course 1411 --module 5 --date 03-15 --midterm

AUTHOR: Steven J Holtz
LAST MODIFIED: 2026-06-29
"""

import sys
import csv
import argparse
import configparser
from datetime import datetime, timedelta
from operator import itemgetter as iGetter
import pathlib

from dateutil.rrule import rrule, rruleset, MO, TU, WE, TH, FR, SA, SU, WEEKLY

# #########################
# Load configuration:

config = configparser.ConfigParser()

if not config.read("config.ini"):
    print(
        "ERROR: Could not open 'config.ini'. Please ensure it "
        "exists in the same directory, has proper permissions, etc.",
        file=sys.stderr,
    )
    sys.exit(1)

# Constants and maps used in configuration processing
CURRENT_YEAR = datetime.now().year

DAY_MAP = {
    "Monday": MO,
    "Tuesday": TU,
    "Wednesday": WE,
    "Thursday": TH,
    "Friday": FR,
    "Saturday": SA,
    "Sunday": SU,
}


# Utility function to process MM-DD strings into datetime objects
def parse_mm_dd(date_str):
    try:
        dt = datetime.strptime(f"{CURRENT_YEAR}-{date_str.strip()}", "%Y-%m-%d")
    except ValueError as e:
        print(f"ERROR: In config.ini reading '{date_str}' string: {e}", file=sys.stderr)
        sys.exit(1)
    return dt


# Process "Course" section of config

# Course prefix or designator, like "CS" for "Computer Science":
COURSE_PREFIX = config.get("Course", "Prefix")

# Course numbers for courses taught:
COURSE_NUMBERS = config.get("Course", "Numbers").split()

# The very first assessment code:
FIRST_ASSESS_CODE = config.get("Course", "First Assess Code")

# Number of modules in the course:
try:
    NUMBER_OF_MODULES = config.getint("Course", "Number of Modules")
except ValueError as e:
    print(f"ERROR: In config.ini reading 'Number of Modules': {e}", file=sys.stderr)
    sys.exit(1)

# Course start and end dates:
COURSE_DATES = [
    parse_mm_dd(date)
    for date in config.get("Course", "Dates").splitlines()
    if date.strip()
]

# Dates to exclude, like Holidays and Spring Break:
EXCLUDE_DATES = [
    parse_mm_dd(date)
    for date in config.get("Course", "Exclude Dates").splitlines()
    if date.strip()
]

# Time that solutions are due (17 == 5:00 PM):
try:
    dt_time = datetime.strptime(config.get("Course", "Due Time").strip(), "%I:%M %p")
    DUE_TIME = timedelta(hours=dt_time.hour, minutes=dt_time.minute)
except ValueError as e:
    print(f"ERROR: In config.ini reading 'Due Time': {e}", file=sys.stderr)
    sys.exit(1)

# Day of the week that quizzes and assignments are due on:
try:
    QUIZ_DUE_DAY_OF_WEEK = DAY_MAP[config.get("Course", "Quiz Due Day").strip()]
except KeyError as e:
    print(f"ERROR: In config.ini reading 'Quiz Due Day': {e}", file=sys.stderr)
    sys.exit(1)

try:
    ASSIGNMENT_DUE_DAY_OF_WEEK = DAY_MAP[
        config.get("Course", "Assignment Due Day").strip()
    ]
except KeyError as e:
    print(f"ERROR: In config.ini reading 'Assignment Due Day': {e}", file=sys.stderr)
    sys.exit(1)

# Time span after which an assessment is no longer worth any credit:
try:
    TOO_LATE_OFFSET = timedelta(weeks=config.getint("Course", "Too Late Offset"))
except ValueError as e:
    print(f"ERROR: In config.ini reading 'Too Late Offset': {e}", file=sys.stderr)
    sys.exit(1)

# Time span after which an assignment can no longer be re-submitted to
# fix errors:
try:
    RESUBMISSION_DEADLINE_OFFSET = timedelta(
        weeks=config.getint("Course", "Resubmission Deadline Offset")
    )
except ValueError as e:
    print(
        f"ERROR: In config.ini reading 'Resubmission Deadline Offset': {e}",
        file=sys.stderr,
    )
    sys.exit(1)

# Default Base path to CSV storage:
DEFAULT_BASE_PATH = config.get("Course", "Base Path")

# Process "Mail Merge" section of config

# Data that needs configured to match the mass email template
# associated with the Thunderbird mail-merge addon:
to_csv = [
    [
        h.strip()
        for h in config.get("Mail Merge", "Headers").strip().splitlines()
        if h.strip()
    ]
]

# Output format for dates in email:
DATE_FORMAT = config.get("Mail Merge", "Date Format")

# #########################


def parse_args():
    parser = argparse.ArgumentParser(
        description="Process Canvas LMS CSV files for input into "
        + "Thunderbird Mail Merge."
    )

    parser.add_argument(
        "-c",
        "--course",
        type=str,
        choices=COURSE_NUMBERS,
        default=COURSE_NUMBERS[0],
        help=f"Course number to process (default: {COURSE_NUMBERS[0]})",
    )

    parser.add_argument(
        "-m",
        "--module",
        type=int,
        help="Current module students are working in (default: "
        + "auto-calculated from relative week number)",
    )

    parser.add_argument(
        "-d",
        "--date",
        type=str,
        help="Month-day (MM-DD) string to match in input "
        + f" filenames. (default: {datetime.now().strftime("%m-%d")})",
    )

    parser.add_argument(
        "--midterm", action="store_true", help="Include midterm alert message flag"
    )

    parser.add_argument(
        "--base-path",
        type=str,
        default=DEFAULT_BASE_PATH,
        help="Path to grades directory where all files are read from "
        + f"and written to (default: {DEFAULT_BASE_PATH})",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Collect due dates and times for all quizzes and assignments:
    quiz_rule_set = rruleset()
    assignment_rule_set = rruleset()

    quiz_rule_set.rrule(
        rrule(
            freq=WEEKLY,
            dtstart=COURSE_DATES[0] + DUE_TIME,
            byweekday=QUIZ_DUE_DAY_OF_WEEK,
            until=COURSE_DATES[1] + DUE_TIME - TOO_LATE_OFFSET,
        )
    )

    assignment_rule_set.rrule(
        rrule(
            freq=WEEKLY,
            dtstart=COURSE_DATES[0] + DUE_TIME + timedelta(weeks=1),
            byweekday=ASSIGNMENT_DUE_DAY_OF_WEEK,
            until=COURSE_DATES[1] + DUE_TIME - timedelta(weeks=1),
        )
    )

    assignment_rule_set.rdate(COURSE_DATES[1] + DUE_TIME + timedelta(weeks=1))

    for a_date in EXCLUDE_DATES:
        quiz_rule_set.exdate(a_date + DUE_TIME)
        assignment_rule_set.exdate(a_date + DUE_TIME)

    quiz_due_dates = list(quiz_rule_set)
    assignment_due_dates = list(assignment_rule_set)

    today_date = datetime.now()

    # Calculate default month-day string
    month_day_str = args.date if args.date else today_date.strftime("%m-%d")

    # Setup Paths
    course = args.course
    base_path = pathlib.Path(args.base_path).expanduser()
    base_path /= COURSE_PREFIX.lower() + str(course)

    if not base_path.exists():
        print(
            f"ERROR: File storage path {base_path} must exist or be mounted!",
            file=sys.stderr,
        )
        sys.exit(1)

    # Calculate current module based on the current week:
    if COURSE_DATES[0].weekday() != 0:  # Not Monday
        start_date = COURSE_DATES[0] - timedelta(days=COURSE_DATES[0].weekday())
    else:
        start_date = COURSE_DATES[0]

    week_number = (today_date - start_date).days // 7
    current_module = args.module if args.module else week_number

    if not (1 <= current_module <= NUMBER_OF_MODULES):
        print(
            f"WARNING: Module {current_module} is outside the expected range (1 - {NUMBER_OF_MODULES}).",
            file=sys.stderr,
        )

    # Date calculations
    try:
        as_of_date = datetime.strptime(
            month_day_str + "-" + str(today_date.year), "%m-%d-%Y"
        )
    except ValueError:
        print(
            f"ERROR: Invalid date format provided '{month_day_str}'. Must be MM-DD.",
            file=sys.stderr,
        )
        sys.exit(1)

    as_of_date_str = as_of_date.strftime("%-m/%-d/%Y")
    midterm_alert = 1 if args.midterm else 0

    print(f"Files will be processed from: {base_path}")

    grades_path_filename = ""
    missing_work_path_filename = ""

    for filename in base_path.iterdir():
        name = filename.name
        ext = filename.suffix
        if (
            grades_path_filename == ""
            and "Grades" in name
            and month_day_str in name
            and ext == ".csv"
        ):
            grades_path_filename = filename
            print(f"\tGrade data:              {grades_path_filename}")
            continue
        if (
            missing_work_path_filename == ""
            and month_day_str in name
            and ext == ".csv"
            and str(name).startswith("missingAssignments")
        ):
            missing_work_path_filename = filename
            print(f"\tMissing assignment data: {missing_work_path_filename}")
            continue
        if grades_path_filename != "" and missing_work_path_filename != "":
            break

    if grades_path_filename == "" or missing_work_path_filename == "":
        print(
            "ERROR: Could not locate both grades and missing assignments files for the specified date.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Process missing work
    missing_work_data = []
    try:
        with missing_work_path_filename.open() as f:
            freader = csv.reader(f)
            next(freader)
            for row in freader:
                missing_work_data.append(list(row))
    except IOError as e:
        print(f"{e.strerror}: {missing_work_path_filename}", file=sys.stderr)
        sys.exit(1)

    missing_work_data.sort(key=iGetter(0))

    # Process grades
    grades_data = []
    try:
        with grades_path_filename.open() as f:
            freader = csv.reader(f)
            next(freader)
            next(freader)
            for row in freader:
                grades_data.append(list(row))
    except IOError as e:
        print(f"{e.strerror}: {grades_path_filename}", file=sys.stderr)
        sys.exit(1)

    # Deadline calculations
    next_quiz_too_late = -1
    next_quiz_too_late_date = -1
    for number, quiz in enumerate(quiz_due_dates, start=1):
        if today_date < quiz + TOO_LATE_OFFSET:
            next_quiz_too_late = number
            next_quiz_too_late_date = (quiz + TOO_LATE_OFFSET).strftime(DATE_FORMAT)
            break

    next_assignment_too_late = -1
    next_assignment_too_late_date = -1
    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + TOO_LATE_OFFSET:
            next_assignment_too_late = number
            next_assignment_too_late_date = (assignment + TOO_LATE_OFFSET).strftime(
                DATE_FORMAT
            )
            break

    next_assignment_resubmit_too_late = -1
    next_assignment_resubmit_too_late_date = -1
    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + RESUBMISSION_DEADLINE_OFFSET:
            next_assignment_resubmit_too_late = number
            next_assignment_resubmit_too_late_date = (
                assignment + RESUBMISSION_DEADLINE_OFFSET
            ).strftime(DATE_FORMAT)
            break

    last_module = current_module
    email = ""
    no_work_done = 0
    nothing_late = 1

    for student in grades_data:
        name = student[0]
        if "Points Possible" in name or "Student, Test" in name:
            continue

        try:
            [last_name, first_name] = name.split(", ")
        except ValueError:
            continue  # Malformed name

        email = student[3]

        for assessment in missing_work_data:
            if assessment[0] != name:
                continue
            if "Feedback Survey" in assessment[5]:
                continue
            nothing_late = 0

            assess_code = assessment[5].split()[1]
            assess = "".join(ch for ch in assess_code if ch.isdigit())
            try:
                assess = int(assess)
            except ValueError:
                continue

            if assess_code.startswith(FIRST_ASSESS_CODE):
                no_work_done = 1

            if assess < last_module:
                last_module = assess

        to_csv.append(
            [
                COURSE_PREFIX + course,
                first_name,
                last_name,
                email,
                as_of_date_str,
                midterm_alert,
                current_module - last_module,
                last_module,
                current_module,
                no_work_done,
                nothing_late,
                next_quiz_too_late,
                next_quiz_too_late_date,
                next_assignment_too_late,
                next_assignment_too_late_date,
                next_assignment_resubmit_too_late,
                next_assignment_resubmit_too_late_date,
            ]
        )

        # Reset for next student
        last_module = current_module
        no_work_done = 0
        nothing_late = 1

    today_path_str = today_date.strftime("status-%Y-%m-%d.csv")
    out_file = base_path / today_path_str

    try:
        with out_file.open("w", newline="") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerows(to_csv)
    except IOError as e:
        print(f"{e.strerror}: {out_file}", file=sys.stderr)
        sys.exit(1)

    print(f"\nSuccessfully generated {out_file}!")


if __name__ == "__main__":
    main()
