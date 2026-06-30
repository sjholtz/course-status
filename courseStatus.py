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
# #########################

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


def parse_mm_dd(date_str):
    """Form `datetime` object.

    Assumes that `date_str` is a string of the form "MM-DD".

    Convert `date_str` into a `datetime` object, using the global
    constant `CURRENT_YEAR` for the year.

    Any `ValueError` exceptions generated result in an error message
    and the program exiting, as this is an unrecoverable error without
    getting a replacement string from the user....
    """
    try:
        dt = datetime.strptime(f"{CURRENT_YEAR}-{date_str.strip()}", "%Y-%m-%d")
    except ValueError as e:
        print(f"ERROR: In config.ini reading '{date_str}' string: {e}", file=sys.stderr)
        sys.exit(1)
    return dt


def convert_day_str_to_rrule(day_str):
    """Map string to dateutil.rrule.weekday.

    Input:
    - `day_str` the sting to map

    Return the `dateutil.rrule.weekday` associated with `day_str`,
    where `day_str` can be a prefix to any day. If the `day_str`
    prefix is ambiguous, like "T" (Tuesday or Thursday?) or "S"
    (Saturday or Sunday?) then raise a ValueError.
    """
    DAY_MAP = {
        "Monday": MO,
        "Tuesday": TU,
        "Wednesday": WE,
        "Thursday": TH,
        "Friday": FR,
        "Saturday": SA,
        "Sunday": SU,
    }

    the_key = None

    for key in DAY_MAP:
        if key.lower().startswith(day_str.lower()):
            if the_key:
                the_key = None
            else:
                the_key = DAY_MAP[key]
            # Need to keep iterating to see if 'day' is a prefix to
            # another key, like day == 'T' or 'S' would.

    if not the_key:
        raise ValueError("Illegal or insufficient due day")

    return the_key


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
    QUIZ_DUE_DAY_OF_WEEK = convert_day_str_to_rrule(
        config.get("Course", "Quiz Due Day").strip()
    )
except ValueError as e:
    print(f"ERROR: In config.ini reading 'Quiz Due Day': {e}", file=sys.stderr)
    sys.exit(1)

try:
    ASSIGNMENT_DUE_DAY_OF_WEEK = convert_day_str_to_rrule(
        config.get("Course", "Assignment Due Day").strip()
    )
except ValueError as e:
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
BASE_CSV_HEADERS = [
    h.strip()
    for h in config.get("Mail Merge", "Headers").strip().splitlines()
    if h.strip()
]

# Output format for dates in email:
DATE_FORMAT = config.get("Mail Merge", "Date Format")

# #########################
# Helper Functions
# #########################


def parse_args():
    """Parse command line arguments and return them."""
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


def generate_due_dates():
    """Calculate due dates and times for all quizzes and assignments.

    Return: A tuple of lists:
    0. The grades data
    1. The missing assignments data
    """
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

    return list(quiz_rule_set), list(assignment_rule_set)


def setup_base_path(course_number, base_path_arg):
    """Resolve and validate the base path directory.

    Return the `Path` object to read from and write to.

    Test if the path exists. If it does not exist, provide a message
    to the user and terminate.
    """
    base_path = pathlib.Path(base_path_arg).expanduser()
    base_path /= COURSE_PREFIX.lower() + str(course_number)

    if not base_path.exists():
        print(
            f"ERROR: File storage path {base_path} must exist or be mounted!",
            file=sys.stderr,
        )
        sys.exit(1)

    return base_path


def calculate_current_module(module_arg, today_date):
    """Calculate current module number.

    Return value is the module_arg inputor it is calculated from the
    number of weeks (starting on Monday) that have passed until today.

    If the module number given or calculated is out-of-range, issue a
    warning to the user.
    """
    if module_arg:
        current_module = module_arg
    else:
        first_day_of_class = COURSE_DATES[0]

        if first_day_of_class.weekday() != 0:  # Not Monday
            # Set start_day to Monday of that first week of class
            start_date = first_day_of_class - timedelta(
                days=first_day_of_class.weekday()
            )
        else:
            start_date = first_day_of_class

        # How many Mondays have passed between today and the start
        # day?
        current_module = ((today_date - start_date).days // 7) + 1

    if not (1 <= current_module <= NUMBER_OF_MODULES):
        print(
            f"WARNING: Module {current_module} is outside the expected range (1 - {NUMBER_OF_MODULES}).",
            file=sys.stderr,
        )

    return current_module


def format_as_of_date(date_arg, today_date):
    """Generate required string formats for needed dates.

    Input:
    - `date_arg` comes from the command line. It is either not set, or
      it must be of the form "MM-DD"
    - `today_date` is a `datetime` object holding today’s date

    This routine returns 3 related values in a tuple:
    0. The "MM-DD" string in `date_str` or `today_date` as a 2-digit
       "MM-DD" string
    1. The "MM/DD/YYYY" string with 1- or 2-digit month and day
       generated from both the `month_day_str` and `today_date.year`
    2. The "YYYY-MM-DD" string 2-digit month and day

    If the "MM-DD-YYYY" `datetime` object is invalid, then the user
    receives an error message and the program terminates.
    """
    month_day_str = date_arg if date_arg else today_date.strftime("%m-%d")

    try:
        as_of_date = datetime.strptime(f"{month_day_str}-{today_date.year}", "%m-%d-%Y")
    except ValueError:
        print(
            f"ERROR: Invalid date format provided '{month_day_str}'. Must be MM-DD.",
            file=sys.stderr,
        )
        sys.exit(1)

    return (
        month_day_str,
        as_of_date.strftime("%-m/%-d/%Y"),
        as_of_date.strftime("%Y-%m-%d"),
    )


def locate_input_files(base_path, month_day_str):
    """Finds the filenames of grades and missing assignments files.

    Input:
    - `base_path` is the `Path` object holding the path to the
      directory where all files are read from
    - `month_day_str` is the "MM-DD" string that must be in both the
      grades and the missing assignments filename

    Returns a tuple containing:
    0. A `Path` object to the "grades" file
    1. A `Path` object to the "missing assignments" file

    If either file cannot be found, the user is issued an error
    message and the program terminates.
    """
    grades_file, missing_work_file = None, None

    for filename in base_path.iterdir():
        name, ext = filename.name, filename.suffix

        if (
            not grades_file
            and "Grades" in name
            and month_day_str in name
            and ext == ".csv"
        ):
            grades_file = filename
            print(f"\tGrade data:              {grades_file}")
        elif (
            not missing_work_file
            and month_day_str in name
            and ext == ".csv"
            and str(name).startswith("missingAssignments")
        ):
            missing_work_file = filename
            print(f"\tMissing assignment data: {missing_work_file}")

    if not grades_file or not missing_work_file:
        print(
            "ERROR: Could not locate both grades and missing assignments files for the specified date.",
            file=sys.stderr,
        )
        sys.exit(1)

    return grades_file, missing_work_file


def read_csv_file(file_path, skip_rows=0):
    """Read a CSV file.

    Input:
    - `file_path` is a `Path` object to the CSV file to read
    - `skip_rows` is the number of header lines to skip over

    Return the data read in as a list of lists.
    """
    data = []
    try:
        with file_path.open() as f:
            freader = csv.reader(f)
            for _ in range(skip_rows):
                next(freader)
            for row in freader:
                data.append(list(row))
    except IOError as e:
        print(f"{e.strerror}: {file_path}", file=sys.stderr)
        sys.exit(1)

    return data


def calculate_deadlines(today_date, quiz_due_dates, assignment_due_dates):
    """Find deadlines for assessments.

    Input:
    - `today_date` is a `datetime` object holding today’s date
    - `quiz_due_dates` is a list of `datetime` objects holding the
      due date and time for all of the quizzes
    - `assignment_due_dates` is a list of `datetime` objects holding
      the due date and time for all of the assignments

    Returns a dictionary that holds the following key/value pairs:
    "next quiz too late": The number of the next quiz that will be too
                          late to turn in, as an int
    "next quiz too late date": The deadline after which the "next quiz
                               too late" cannot be turned in, as a
                               string
    "next assignment too late": The number of the next assignment that
                                will be too late to turn in, as an int
    "next assignment too late date": The deadline after which the
                                     "next assignment too late" cannot
                                     be turned in, as a string
    "next assignment resubmit too late": The number of the next
                                         assignment that will be too
                                         late to resubmit, as an int
    "next assignment resubmit too late date": The deadline after which
                                              the "next assignment
                                              resubmit too late"
                                              cannot be turned in, as
                                              a string
    """
    deadlines = {
        "next quiz too late": -1,
        "next quiz too late date": "",
        "next assignment too late": -1,
        "next assignment too late date": "",
        "next assignment resubmit too late": -1,
        "next assignment resubmit too late date": "",
    }

    for number, quiz in enumerate(quiz_due_dates, start=1):
        if today_date < quiz + TOO_LATE_OFFSET:
            deadlines["next quiz too late"] = number
            deadlines["next quiz too late date"] = (quiz + TOO_LATE_OFFSET).strftime(
                DATE_FORMAT
            )
            break

    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + TOO_LATE_OFFSET:
            deadlines["next assignment too late"] = number
            deadlines["next assignment too late date"] = (
                assignment + TOO_LATE_OFFSET
            ).strftime(DATE_FORMAT)
            break

    for number, assignment in enumerate(assignment_due_dates, start=1):
        if today_date < assignment + RESUBMISSION_DEADLINE_OFFSET:
            deadlines["next assignment resubmit too late"] = number
            deadlines["next assignment resubmit too late date"] = (
                assignment + RESUBMISSION_DEADLINE_OFFSET
            ).strftime(DATE_FORMAT)
            break

    return deadlines


def process_student_data(
    grades_data,
    missing_work_data,
    current_module,
    course_number,
    as_of_date_str,
    is_midterm_alert,
    deadlines,
):
    """Processes data to generate rows for CSV file output.

    Input:
    - `grades_data` students grades data
    - `missing_work_data` student missing assignments data
    - `current_module` is the module students are working in
    - `course_number` is the course number
    - `as_of_date_str` the date being processed to
    - `is_midterm_alert` is there a midterm alert approaching?
    - `deadlines` the deadlines that are approaching

    Return a list of lists containing student data, aligned under Mail
    Merge headings, ready to be written to CSV file.
    """
    output_rows = []

    for student in grades_data:
        name = student[0]
        if "Points Possible" in name or "Student, Test" in name:
            continue

        try:
            last_name, first_name = name.split(", ")
        except ValueError:
            continue  # Malformed name

        email = student[3]

        last_module = current_module
        no_work_done = 0  # False, assume this student is working
        nothing_late = 1  # True, assume this student's work is up-to-date

        for assessment in missing_work_data:
            if assessment[0] != name or "Feedback Survey" in assessment[5]:
                continue

            nothing_late = 0  # False, prove there is nothing late

            assess_code = assessment[5].split()[1]
            assess_number = "".join(ch for ch in assess_code if ch.isdigit())

            try:
                assess_number = int(assess_number)
            except ValueError:
                continue

            if assess_code.startswith(FIRST_ASSESS_CODE):
                no_work_done = 1  # True, if this assessment starts
                # with `FIRST_ASSESS_CODE` then this student has no
                # work done.

            if assess_number < last_module:
                last_module = assess_number

        output_rows.append(
            [
                COURSE_PREFIX + course_number,
                first_name,
                last_name,
                email,
                as_of_date_str,
                is_midterm_alert,
                current_module - last_module,
                last_module,
                current_module,
                no_work_done,
                nothing_late,
                deadlines["next quiz too late"],
                deadlines["next quiz too late date"],
                deadlines["next assignment too late"],
                deadlines["next assignment too late date"],
                deadlines["next assignment resubmit too late"],
                deadlines["next assignment resubmit too late date"],
            ]
        )

    return output_rows


def write_csv_data(out_file, data):
    """Write mail merge ready data to CSV output file.

    Input:
    - `out_file` is a `Path` object holding the file to write to
    - `data` is the data to write to the CSV file

    If the is an error opening the file, report the error to the user
    and terminate the program.
    """
    try:
        with out_file.open("w", newline="") as f:
            writer = csv.writer(f, dialect="unix")
            writer.writerows(data)
    except IOError as e:
        print(f"{e.strerror}: {out_file}", file=sys.stderr)
        sys.exit(1)


def main():
    args = parse_args()

    # Setup
    quiz_due_dates, assignment_due_dates = generate_due_dates()

    base_path = setup_base_path(args.course, args.base_path)

    today_date = datetime.now()

    current_module = calculate_current_module(args.module, today_date)

    month_day_str, as_of_date_str, out_file_str = format_as_of_date(
        args.date, today_date
    )

    midterm_alert = 1 if args.midterm else 0

    # Locate and parse files
    print(f"Files will be processed from: {base_path}")

    grades_file, missing_file = locate_input_files(base_path, month_day_str)

    missing_work_data = read_csv_file(missing_file, skip_rows=1)
    # Sort the missing assignments data by name (the first column)
    missing_work_data.sort(key=iGetter(0))

    grades_data = read_csv_file(grades_file, skip_rows=3)

    # Calculate assessment deadlines
    deadlines = calculate_deadlines(today_date, quiz_due_dates, assignment_due_dates)

    # Process data into rows for output
    student_rows = process_student_data(
        grades_data,
        missing_work_data,
        current_module,
        args.course,
        as_of_date_str,
        midterm_alert,
        deadlines,
    )

    # Collect CSV headers and data together
    final_csv_data = [list(BASE_CSV_HEADERS)]
    final_csv_data.extend(student_rows)

    # Write data to CSV output
    out_file = base_path / f"status-{out_file_str}.csv"

    write_csv_data(out_file, final_csv_data)

    print(f"\nSuccessfully generated {out_file}!")


if __name__ == "__main__":
    main()
