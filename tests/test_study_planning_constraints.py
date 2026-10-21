from datetime import datetime, time

from src.planning_validation import PlanBlock, PlanningConstraints, WorkRequirement, validate_plan


def at(day, time):
    return datetime.fromisoformat(f"2026-10-{day:02d}T{time}")


def block(task, day, start, end, category="work"):
    return PlanBlock(task, at(day, start), at(day, end), category)


def constraints():
    return PlanningConstraints(
        now=at(17, "20:18"),
        fixed=[
            block("Sunday 5k", 18, "11:00", "12:00", "exercise"),
            block("Wednesday class", 21, "09:00", "11:30"),
            block("Drive home", 21, "11:30", "12:00", "travel"),
            block("Wednesday class", 21, "16:00", "16:45"),
            block("Running class", 21, "18:00", "20:00", "exercise"),
            block("Swimming", 20, "19:30", "21:30", "exercise"),
            block("Swimming", 22, "19:30", "21:30", "exercise"),
            block("Brother", 23, "08:00", "12:00"),
        ],
        work=[
            WorkRequirement("Clinical paper", at(22, "23:00"), 180),
            WorkRequirement("Thesis plan", at(25, "23:00"), 180),
            WorkRequirement("Sex psychology revision", at(22, "08:00"), 120),
            WorkRequirement("Clinical psychology revision", at(24, "09:00"), 360),
        ],
        awake_windows={
            at(day, "00:00").date(): (time(9 if at(day, "00:00").weekday() >= 5 else 7 if day == 22 else 8), time(23))
            for day in range(17, 26)
        },
        required_exercise_days=[at(17, "00:00").date()],
        unknown_times=["Oct 22 exam", "Oct 24 exam", "Walk home after 5k", "Exam travel"],
    )


def test_incident_errors_are_independent_of_retrieval():
    limits = constraints()
    invalid = limits.fixed + [
        block("Clinical paper", 23, "18:00", "21:00"),
        block("Extra run", 22, "17:00", "18:00", "exercise"),
        block("Study", 17, "18:00", "19:00"),
        block("Invented subject", 21, "11:30", "12:00"),
    ]
    issues = validate_plan(limits, invalid)
    assert "Work after deadline: Clinical paper" in issues
    assert "Insufficient time before deadline: Clinical paper" in issues
    assert "Additional exercise on class day: 2026-10-22" in issues
    assert "Elapsed time: Study" in issues
    assert any("Overlap:" in issue and "Drive home" in issue for issue in issues)
    assert "Unknown time: Oct 22 exam" in issues
    assert "Unknown time: Walk home after 5k" in issues


def test_revision_preserves_paper_deadline_and_fixed_constraints():
    limits = constraints()
    planned = limits.fixed + [
        block("Clinical paper", 19, "12:00", "15:00"),
        block("Evening run", 17, "21:00", "22:00", "exercise"),
        block("Thesis plan", 24, "14:00", "17:00"),
        block("Sex psychology revision", 19, "15:00", "17:00"),
        block("Clinical psychology revision", 20, "09:00", "15:00"),
    ]
    assert validate_plan(limits, planned) == [f"Unknown time: {name}" for name in limits.unknown_times]
    revised = [item for item in planned if item.task != "Clinical paper"]
    assert "Insufficient time before deadline: Clinical paper" in validate_plan(limits, revised)
    revised.remove(limits.fixed[2])
    assert "Missing fixed commitment: Drive home" in validate_plan(limits, revised)


def test_sleep_and_exercise_constraints_are_checked():
    limits = constraints()
    issues = validate_plan(limits, [block("Too early", 18, "08:00", "09:00"), block("Too late", 19, "22:30", "23:30")])
    assert "Outside waking hours: Too early" in issues
    assert "Outside waking hours: Too late" in issues
    assert "Missing exercise time: 2026-10-17" in issues
