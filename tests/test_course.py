from datetime import datetime, time
from courseStatus import AppConfig, Course


def test_course_initialize_dynamic_modules(app_config: AppConfig) -> None:
    """Tests that the Course structure accurately generates all dynamic assignments."""
    course = Course(app_config, 2026)
    modules = course.modules

    # Module 1 has Quizzes, Assignments, and Geditr
    assert 1 in modules
    assert modules[1].get_assessment("Quizzes") is not None
    assert modules[1].get_assessment("Assignments") is not None

    geditr1 = modules[1].get_assessment("Geditr")
    assert geditr1 is not None
    assert geditr1.due_date.time() == time(2, 0)
    assert geditr1.due_date.weekday() == 5  # Saturday

    # Module 13 only has Geditr
    assert 13 in modules
    assert modules[13].get_assessment("Quizzes") is None
    assert modules[13].get_assessment("Assignments") is None
    assert modules[13].get_assessment("Geditr") is not None

    # Finals Week
    assert "f" in modules
    final_quiz = modules["f"].get_assessment("Quizzes")
    final_geditr = modules["f"].get_assessment("Geditr")

    assert final_quiz is not None
    assert final_quiz.is_final is True

    assert final_geditr is not None
    assert final_geditr.due_date.time() == time(4, 0)
    assert final_geditr.due_date.weekday() == 1  # Tuesday


def test_module_5_dates_and_assessments(app_config: AppConfig) -> None:
    """Verifies that Module 5 dates correspond to the week of June 1-5, 2026."""
    course = Course(app_config, 2026)

    mod5 = course.get_module(5)
    assert mod5 is not None

    quiz = mod5.get_assessment("Quizzes")
    assign = mod5.get_assessment("Assignments")

    assert quiz is not None
    assert quiz.due_date == datetime(2026, 6, 5, 17, 0)

    assert assign is not None
    assert assign.due_date == datetime(2026, 6, 3, 17, 0)
