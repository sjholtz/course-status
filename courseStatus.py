#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

# courseStatus takes the most recent Canvas CSV grades and missing
# assignments report files and generates a CSV file used as input to
# the Thunderbird mail-merge addon. (https://addons.thunderbird.net/addon/mail-merge/).

import sys
import csv
from datetime import datetime, timedelta
from dateutil.rrule import rrule, rruleset, MO, TU, WE, TH, FR, SA, SU, WEEKLY
from calendar import isleap
from operator import itemgetter as iGetter
import pathlib

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
course_dates = [datetime(2026, 1, 14), datetime(2026, 5, 1)]

# Dates to exclude, like Holidays and Spring Break:
exclude_dates = [
    datetime(2026, 1, 19),  # MLK day
    datetime(2026, 3, 9),   # Spring Break Monday
    datetime(2026, 3, 10),  # Spring Break Tuesday
    datetime(2026, 3, 11),  # Spring Break Wednesday
    datetime(2026, 3, 12),  # Spring Break Thursday
    datetime(2026, 3, 13),
]  # Spring Break Friday

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

# Base path to CSV storage:
base_path = pathlib.Path("~/Private/grades").expanduser()

# #########################
# Data that needs configured to match the mass email template
# associated with the Thunderbird mail-merge addon:

# A list of lists of the data that will be written to the CSV file
# used as input to mail-merge.
#
# This first nested list contains the headers for the columns that
# will be added later, and act as the field names in the mail-merge
# email template.
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

# Collect due dates and times for all quizzes and assignments:
quiz_rule_set = rruleset()
assignment_rule_set = rruleset()

# A quiz is due each week until 2 weeks before end is course:
quiz_rule_set.rrule(
    rrule(
        freq=WEEKLY,
        dtstart=course_dates[0] + due_time,
        byweekday=quiz_due_day_of_week,
        until=course_dates[1] + due_time - too_late_offset,
    )
)

# An assignment is due each week from week 2 until the week before
# finals week:
assignment_rule_set.rrule(
    rrule(
        freq=WEEKLY,
        dtstart=course_dates[0] + due_time + timedelta(weeks=1),
        byweekday=assignment_due_day_of_week,
        until=course_dates[1] + due_time - timedelta(weeks=1),
    )
)

# The last assignment is due the last day of finals week:
assignment_rule_set.rdate(course_dates[1] + due_time + timedelta(weeks=1))

# Exclude due dates where there is no class:
for a_date in exclude_dates:
    quiz_rule_set.exdate(a_date + due_time)
    assignment_rule_set.exdate(a_date + due_time)

quiz_due_dates = list(quiz_rule_set)
assignment_due_dates = list(assignment_rule_set)

# Today's date:
today_date = datetime.now()
# As a m/d/yyyy string:
today_str = today_date.strftime("%-m/%-d/%Y")
# As a mm-dd string:
month_day_str = today_date.strftime("%m-%d")

# #########################

# Build a menu-like prompt string and a list of validate menu choices:
print("Which course:")
valid_choices = []
for number, course in enumerate(course_numbers):
    print(f"\t{number}) {course_prefix}{course}")
    valid_choices.append(str(number))

# Get the user's choice of course:
choice = input("Choice [0]: ")

# If no choice provided, use 0 (zero):
if not choice:
    choice = "0"

# Set the chosen course and adjust base path while validating the
# choice:
if choice in valid_choices:
    course = course_numbers[int(choice)]
    base_path /= course_prefix.lower() + str(course)
else:
    print("Invalid course: exiting.", file=sys.stderr)
    sys.exit(1)

print()

# Make sure base path exists:
if not base_path.exists():
    print("ERROR: File storage path must be exist or be mounted!!!", file=sys.stderr)
    sys.exit(1)

# Calculate current module based on the current week:
if course_dates[0].weekday() != 0:  # Not Monday
    start_date = course_dates[0] - timedelta(days=course_dates[0].weekday())
else:
    start_date = course_dates[0]

week_number = (today_date - start_date).days // 7

current_module = input(f"Current module students are working in [{week_number}]? ")

# If the user provided no input, use the provided week number:
if not current_module:
    current_module = week_number

# Convert current_module to int and make sure it is reasonable (note
# that it could still be in incorrect!):
while True:
    try:
        current_module = int(current_module)
        if 1 <= current_module <= number_of_modules:
            break
        else:
            current_module = input(
                f"ERROR: Current module students are working in [{week_number}]? "
            )
    except ValueError:
        current_module = input(
            f"ERROR: Current module students are working in ({week_number})? "
        )

    # If the user provided no input, use the provided week number:
    if not current_module:
        current_module = week_number

print()

# Get the MM-DD string embedded in the CSV files that will be opened
# for processing:


def get_month_day_str(mm_dd, *, error=False):
    # Error message, or not:
    message = "ERROR: " if error else ""

    # Get user input:
    string = input(
        message
        + f"Enter the month-day in missing assessments and grades files [{mm_dd}]: "
    )

    # If no user input, return the mm_dd string provided:
    if not string:
        return mm_dd
    # Else
    return string


input_str = get_month_day_str(month_day_str)

# Error check the MM-DD string provided. Note that classes are held in
# the following months: 01, 02, 03, 04, 05 (Spring term) and 08, 09,
# 10, 11, 12 (Fall term):
while True:
    # String must be of length 5:
    if len(input_str) != 5:
        input_str = get_month_day_str(month_day_str, error=True)
    # First digit (first month digit) must be a '0' or a '1':
    elif input_str[0] < "0" or input_str[0] > "1":
        input_str = get_month_day_str(month_day_str, error=True)
    # Second digit (second month digit) can be any digit:
    elif not input_str[1].isdigit():
        input_str = get_month_day_str(month_day_str, error=True)
    # The third character must be a hyphen:
    elif input_str[2] != "-":
        input_str = get_month_day_str(month_day_str, error=True)
    # The fourth digit (first day digit) must be between '0' and '3'
    # inclusive, as the longest month contains 31 days:
    elif input_str[3] < "0" or input_str[3] > "3":
        input_str = get_month_day_str(month_day_str, error=True)
    # The last digit (second day digit) can be any digit:
    elif not input_str[4].isdigit():
        input_str = get_month_day_str(month_day_str, error=True)
    # Check month specific issues:
    elif input_str[0:2] == "02":  # February
        if input_str[3] == "3":  # First day digit cannot be '3'
            input_str = get_month_day_str(month_day_str, error=True)
        elif input_str[3:5] == "29" and not isleap(today_date.year):
            input_str = get_month_day_str(month_day_str, error=True)
    # Months cannot have more than 31 days:
    elif input_str[3] == "3" and input_str[4] > "1":
        input_str = get_month_day_str(month_day_str, error=True)
    # April (04), June (06), September(09), and November (11) have 30 days:
    elif (
        input_str[0:2] in ["04", "06", "09", "11"]
        and input_str[3] == "3"
        and input_str[4] > "0"
    ):
        input_str = get_month_day_str(month_day_str, error=True)
    # The first day of any month is '01':
    elif input_str[3:5] == "00":
        input_str = get_month_day_str(month_day_str, error=True)
    # Else, all tests pass!
    else:
        month_day_str = input_str
        break

print()

# Get the MM-DD string into a datetime with this year:
as_of_date = datetime.strptime(month_day_str + "-" + str(today_date.year), "%m-%d-%Y")
# Format that datetime as a string
as_of_date_str = as_of_date.strftime("%-m/%-d/%Y")

# Is this for a midterm alert?
midterm_alert = 0  # False
choice = input("Include midterm alert message (Y)es|(N)o [N]? ")
if not choice:
    choice = "N"
if choice == "Y" or choice == "y":
    midterm_alert = 1  # True


print()

# Let user know what the working directory is:
print(f"Files will be processed from: {base_path}")

# These will store the names of the CSV files that will be used as
# input:
grades_path_filename = ""
missing_work_path_filename = ""

# Iterate this directory looking for the Canvas CSV files we need.
# These files need to be downloaded from Canvas before execution.
#
# Note that the grades file from Canvas is named like:
#  2026-01-21T1521_Grades-CS_1151_(001).csv
# Produce this file by going to the Canvas gradebook and click the
# "Export" button and then "Export Entire Gradebook."
# Use this filename as Canvas provides it.
#
# And the missing work CSV file like this:
#  missingAssignments-01-21-2026.csv
# Produce this file by going to the Canvas home page for the course,
# click on "Course Analytics" button, click the "Reports" tab, and
# click "Run Report" on the "Missing Assignments" row.
# This filename often needs to be adjusted. Replace spaces with
# hyphens and make sure single digit months or days have a leading
# zero.
for filename in base_path.iterdir():
    name = filename.name
    ext = filename.suffix
    # Get the first (latest date) grades CSV file:
    if (
        grades_path_filename == ""
        and "Grades" in name
        and month_day_str in name
        and ext == ".csv"
    ):
        grades_path_filename = filename
        print(f"\tGrade data:              {grades_path_filename}")
        continue
    # Get the first (latest date) missing work CSV file:
    if (
        missing_work_path_filename == ""
        and month_day_str in name
        and ext == ".csv"
        and str(name).startswith("missingAssignments")
    ):
        missing_work_path_filename = filename
        print(f"\tMissing assignment data: {missing_work_path_filename}")
        continue
    # Quit if we have both of these files set:
    if grades_path_filename != "" and missing_work_path_filename != "":
        break

# Check with the user that both of these files look OK:
if grades_path_filename == "" or missing_work_path_filename == "":
    print(
        "ERROR: Download grades and missing assignments files "
        + "- or re-run and alter the month-day that you provide "
        + "to match your files",
        file=sys.stderr,
    )
    sys.exit(1)
else:
    choice = input("\nIs everything correct (Y)es|(N)o  [Y]? ")
    if not choice:
        choice = "Y"
    if choice != "Y" and choice != "y":
        print(
            "Everything is not OK: Quitting... "
            + "Download required files, or re-run with "
            + "adjusted month-day.",
            file=sys.stderr,
        )
        sys.exit(0)

print()

# Get the data associated with missing student work:
missing_work_data = []

try:  # To open the missing work file:
    f = missing_work_path_filename.open()
except IOError as e:
    print(f"{e.strerror}: {missing_work_path_filename}", file=sys.stderr)
    print("\tGenerate a missing work report from Canvas", file=sys.stderr)
    print(
        "\tand rename it something like: missingAssignments-01-19-2023.csv.",
        file=sys.stderr,
    )
    print(
        "\tso that it has the correct MM-DD (month-day) string in it.", file=sys.stderr
    )
    sys.exit(1)
else:  # the file opened:
    freader = csv.reader(f)
    # Skip the header row:
    next(freader)
    for row in freader:
        missing_work_data.append(list(row))
    f.close()

# Sort the missing work data by student name to make it easier to read:
missing_work_data.sort(key=iGetter(0))

# Get the data associated with student grades:
grades_data = []

try:  # To open this file:
    f = grades_path_filename.open()
except IOError as e:
    print(f"{e.strerror}: {grades_path_filename}", file=sys.stderr)
    print("ERROR: No grades file exists.", file=sys.stderr)
    print("\tExport a gradebook from Canvas.", file=sys.stderr)
    sys.exit(1)
else:
    freader = csv.reader(f)
    # Skip two header rows:
    next(freader)
    next(freader)
    for row in freader:
        grades_data.append(list(row))
    f.close()

# Get the next module number of the quiz and assignment that is going
# to be too late, and the date that it is too late. This will be used
# in the email message presented to the student:

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

# Generate the CSV file that will be read in by the Thunderbird
# mail-merge addon:

# Set defaults for processing output data:
#
# The last module that a student has completed:
last_module = current_module
# Student's email address:
email = ""
# Note 0 and 1 mean "False" and "True" once in the Thunderbird
# mail-merge:
no_work_done = 0  # False
nothing_late = 1  # True

# For each student in the gradebook:
for student in grades_data:
    name = student[0]
    # Skip non-student entries:
    if "Points Possible" in name:
        continue
    if "Student, Test" in name:
        continue

    # Extract this student's first and last names:
    [last_name, first_name] = name.split(", ")

    # Get the student's email address:
    email = student[3]

    # Look for this student in the missing work data:
    for assessment in missing_work_data:
        # Skip data that is not associated with this student:
        if assessment[0] != name:
            continue
        # Skip "Feedback Surveys" as they are not graded assessments
        if "Feedback Survey" in assessment[5]:
            continue
        # There is late work:
        nothing_late = 0  # False

        # Get the assessment code from the title of the assessment. A
        # title looks like "CS1151 CODE: Title", so the second 'field'
        # after splitting on spaces:
        assess_code = assessment[5].split()[1]

        # Assessment codes look like "Q1a" or "A5" where the digit is
        # the module number (or the assessment number). Extract this
        # and convert it to an int:
        assess = ""
        assess = "".join(ch for ch in assess_code if ch.isdigit())
        try:
            assess = int(assess)
        except ValueError:
            continue

        # If this is the very first assessment in the course, then
        # this student has not done any work at all:
        if assess_code.startswith(first_assess_code):
            no_work_done = 1  # True

        # The module associated with this assessment is less than the
        # last module completed by this student, then save this module
        # as the last one completed:
        if assess < last_module:
            last_module = assess

    # Append this student's data to the output list. Note that the
    # labels on the right are the labels used in the Thunderbird
    # mail-merge email template:
    to_csv.append(
        [
            course_prefix + course,  # Course
            first_name,  # FirstName
            last_name,  # LastName
            email,  # Email
            as_of_date_str,  # Date
            midterm_alert,  # MidtermAlert
            current_module - last_module,  # NumberOfModulesBehind
            last_module,  # YouAreInModule
            current_module,  # YouShouldBeInModule
            no_work_done,  # NoWorkDone
            nothing_late,  # NothingLate
            next_quiz_too_late,  # NextQuizTooLate
            next_quiz_too_late_date,  # NextQuizTooLateDate
            next_assignment_too_late,  # NextAssignmentTooLate
            next_assignment_too_late_date,  # NextAssignmentTooLateDate
            next_assignment_resubmit_too_late,  # NextAssignmentResubit
            next_assignment_resubmit_too_late_date,
        ]
    )  # ResubmitDeadLine

    # Reset data for the next student:
    last_module = current_module
    no_work_done = 0  # False
    nothing_late = 1  # True

# The file name to output to:
today_path_str = today_date.strftime("status-%Y-%m-%d.csv")

try:  # To open the file for writing:
    f = (base_path / today_path_str).open("w", newline="")
except IOError as e:
    print(f"{e.strerror}: {base_path / today_path_str}", file=sys.stderr)
    sys.exit(1)
else:
    writer = csv.writer(f, dialect="unix")
    writer.writerows(to_csv)
    f.close()

print("\nAll Done! Have a great day!")
