#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

"""courseStatus.py

Processes the most recent Canvas LMS gradebook and missing assignments
report CSV files into a CSV file used as input to the Thunderbird Mail
Merge add on. (https://addons.thunderbird.net/addon/mail-merge/).

DEPENDENCIES:
 - Standard Libraries: sys, csv, argparse, datetime, operator, pathlib
 - Third-Party Packages: dateutil

USAGE EXAMPLES:
  # Run with all defaults (Course index 0, current week module, today's date)
  $ python3 courseStatus.py

  # Run for course 1411, module 5, specific date, and include midterm alert
  $ python3 courseStatus.py --course 1411 --module 5 --date 03-15 --midterm

AUTHOR: Steven J Holtz
LAST MODIFIED: 2026-06-26
"""

import sys
import csv
import argparse
from datetime import datetime, timedelta
from operator import itemgetter as iGetter
import pathlib

from dateutil.rrule import rrule, rruleset, MO, TU, WE, TH, FR, SA, SU, WEEKLY

# #########################
# Data that needs to be configured for each semester:

# Course prefix:
course_prefix = "CS"  # Computer Science courses

# Course numbers for courses taught:
course_numbers = ["1151", "1411"]

# The very first assessment code:
first_assess_code = "Q1a"

# Number of modules in the course:
number_of_modules = 14

# Course start and end dates:
course_dates = [datetime(2026, 5, 14), datetime(2026, 9, 1)]

# Dates to exclude, like Holidays and Spring Break:
exclude_dates = [
    datetime(2026, 5, 19),  # Fake holiday
    datetime(2026, 7, 9),  # Spring Break Monday
    datetime(2026, 7, 10),  # Spring Break Tuesday
    datetime(2026, 7, 11),  # Spring Break Wednesday
    datetime(2026, 7, 12),  # Spring Break Thursday
    datetime(2026, 7, 13),  # Spring Break Friday
]

# Time that solutions are due (17 == 5:00 PM):
due_time = timedelta(hours=17)

# Day of the week that quizzes and assignments are due on:
quiz_due_day_of_week = FR
assignment_due_day_of_week = WE

# Time span after which an assessment is no longer worth any credit:
too_late_offset = timedelta(weeks=2)

# Time span after which an assignment can no longer be re-submitted to
# fix errors:
resubmission_deadline_offset = timedelta(weeks=3)

# Default Base path to CSV storage:
default_base_path = "~/Private/grades"

# #########################
# Data that needs configured to match the mass email template
# associated with the Thunderbird mail-merge addon:
to_csv = [
    [
        "Course",
        "FirstName",
        "LastName",
        "Email",
        "Date",
        "MidtermAlert",
        "NumberOfModulesBehind",
        "YouAreInModule",
        "YouShouldBeInModule",
        "NoWorkDone",
        "NothingLate",
        "NextQuizTooLate",
        "NextQuizTooLateDate",
        "NextAssignmentTooLate",
        "NextAssignmentTooLateDate",
        "NextAssignmentResubmit",
        "ResubmitDeadLine",
    ]
]

# Output format for dates in email:
date_format = "%-I:%M %p CT on %A %-d %B %Y"

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
        choices=course_numbers,
        default=course_numbers[0],
        help=f"Course number to process (default: {course_numbers[0]})"
    )

    parser.add_argument(
        "-m",
        "--module",
        type=int,
        help="Current module students are working in (default: "
        + "auto-calculated from relative week number)"
    )

    parser.add_argument(
        "-d",
        "--date",
        type=str,
        help="Month-day (MM-DD) string to match in input "
        + f" filenames. (default: {datetime.today().strftime("%m-%d")})"
    )

    parser.add_argument(
        "--midterm",
        action="store_true",
        help="Include midterm alert message flag"
    )

    parser.add_argument(
        "--base-path",
        type=str,
        default=default_base_path,
        help="Path to grades directory where all files are read from "
        + f"written to (default: {default_base_path})"
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
            dtstart=course_dates[0] + due_time,
            byweekday=quiz_due_day_of_week,
            until=course_dates[1] + due_time - too_late_offset,
        )
    )

    assignment_rule_set.rrule(
        rrule(
            freq=WEEKLY,
            dtstart=course_dates[0] + due_time + timedelta(weeks=1),
            byweekday=assignment_due_day_of_week,
            until=course_dates[1] + due_time - timedelta(weeks=1),
        )
    )

    assignment_rule_set.rdate(course_dates[1] + due_time + timedelta(weeks=1))

    for a_date in exclude_dates:
        quiz_rule_set.exdate(a_date + due_time)
        assignment_rule_set.exdate(a_date + due_time)

    quiz_due_dates = list(quiz_rule_set)
    assignment_due_dates = list(assignment_rule_set)

    today_date = datetime.now()

    # Calculate default month-day string
    month_day_str = args.date if args.date else today_date.strftime("%m-%d")

    # Setup Paths
    course = args.course
    base_path = pathlib.Path(args.base_path).expanduser()
    base_path /= course_prefix.lower() + str(course)

    if not base_path.exists():
        print(
            f"ERROR: File storage path {base_path} must exist or be mounted!",
            file=sys.stderr,
        )
        sys.exit(1)

    # Calculate current module based on the current week:
    if course_dates[0].weekday() != 0:  # Not Monday
        start_date = course_dates[0] - timedelta(days=course_dates[0].weekday())
    else:
        start_date = course_dates[0]

    week_number = (today_date - start_date).days // 7
    current_module = args.module if args.module else week_number

    if not (1 <= current_module <= number_of_modules):
        print(
            f"WARNING: Module {current_module} is outside the expected range (1-{number_of_modules}).",
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
        if today_date < quiz + too_late_offset:
            next_quiz_too_late = number
            next_quiz_too_late_date = (quiz + too_late_offset).strftime(date_format)
            break

    next_assignment_too_late = -1
    next_assignment_too_late_date = -1
    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + too_late_offset:
            next_assignment_too_late = number
            next_assignment_too_late_date = (assignment + too_late_offset).strftime(
                date_format
            )
            break

    next_assignment_resubmit_too_late = -1
    next_assignment_resubmit_too_late_date = -1
    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + resubmission_deadline_offset:
            next_assignment_resubmit_too_late = number
            next_assignment_resubmit_too_late_date = (
                assignment + resubmission_deadline_offset
            ).strftime(date_format)
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

            if assess_code.startswith(first_assess_code):
                no_work_done = 1

            if assess < last_module:
                last_module = assess

        to_csv.append(
            [
                course_prefix + course,
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
