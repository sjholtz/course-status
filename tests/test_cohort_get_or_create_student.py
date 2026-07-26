from courseStatus import Cohort, AppConfig, Student

def test_cohort_get_or_create_student(app_config: AppConfig) -> None:
    """Tests the get_or_create_student method to ensure no duplicates are made."""
    cohort: Cohort = Cohort(app_config, 1151, 3, "02-15-2026", 1, 2026)
    student1: Student = cohort.get_or_create_student("Doe, John",
                                                     "jdoe@university.edu")
    student2: Student = cohort.get_or_create_student("Doe, John",
                                                     "jdoe@university.edu")

    assert student1 is student2
    assert len(cohort._students) == 1
