"""Deterministic checks for explicit constraints, independent of model generation."""

from dataclasses import dataclass, field
from datetime import date, datetime, time

PLANNING_GUIDANCE = (
    "For schedules and study plans, maintain an explicit ledger of the user's constraints across revisions. "
    "Preserve deadlines, required work, fixed classes, exercise, travel, wake and sleep times. "
    "Never allocate elapsed time as future work. Never put unfinished work after its deadline. "
    "Reserve actual exam blocks; if exam or travel times are unknown, label them unknown and ask "
    "one follow-up at a time before claiming the plan is complete. Do not invent class subjects. "
    "Swimming or running classes count toward exercise; do not add a second workout unless requested. "
    "Check overlaps and verify that prose descriptions agree with the schedule. A document search "
    "does not validate the plan or prove that every deadline was found."
)


@dataclass(frozen=True)
class PlanBlock:
    task: str
    start: datetime
    end: datetime
    category: str = "work"


@dataclass(frozen=True)
class WorkRequirement:
    task: str
    deadline: datetime
    minutes: int


@dataclass
class PlanningConstraints:
    now: datetime
    fixed: list[PlanBlock] = field(default_factory=list)
    work: list[WorkRequirement] = field(default_factory=list)
    unknown_times: list[str] = field(default_factory=list)
    exercise_minutes_per_day: int = 60
    required_exercise_days: list[date] = field(default_factory=list)
    awake_windows: dict[date, tuple[time, time]] = field(default_factory=dict)


def validate_plan(constraints: PlanningConstraints, blocks: list[PlanBlock]) -> list[str]:
    issues = [f"Unknown time: {name}" for name in constraints.unknown_times]
    for block in blocks:
        if block.end <= block.start:
            issues.append(f"Invalid interval: {block.task}")
        if block.start < constraints.now:
            issues.append(f"Elapsed time: {block.task}")
        awake = constraints.awake_windows.get(block.start.date())
        if awake and (block.start.time() < awake[0] or block.end.time() > awake[1] or block.start.date() != block.end.date()):
            issues.append(f"Outside waking hours: {block.task}")
    ordered = sorted(blocks, key=lambda block: block.start)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            if second.start >= first.end:
                break
            issues.append(f"Overlap: {first.task} / {second.task}")
    for fixed in constraints.fixed:
        if fixed.end <= constraints.now:
            continue
        if fixed not in blocks:
            issues.append(f"Missing fixed commitment: {fixed.task}")
    for requirement in constraints.work:
        scheduled = [block for block in blocks if block.task == requirement.task]
        minutes = sum(
            (block.end - block.start).total_seconds() / 60
            for block in scheduled
            if constraints.now <= block.start < block.end <= requirement.deadline
        )
        if minutes < requirement.minutes:
            issues.append(f"Insufficient time before deadline: {requirement.task}")
        if any(block.end > requirement.deadline for block in scheduled):
            issues.append(f"Work after deadline: {requirement.task}")
    exercise_by_day = {}
    for block in blocks:
        if block.category != "exercise":
            continue
        exercise_by_day.setdefault(block.start.date(), []).append(block)
    for day in constraints.required_exercise_days:
        workouts = exercise_by_day.get(day, [])
        minutes = sum((block.end - block.start).total_seconds() / 60 for block in workouts)
        if minutes < constraints.exercise_minutes_per_day:
            issues.append(f"Missing exercise time: {day}")
    for day, workouts in exercise_by_day.items():
        fixed_workouts = [block for block in constraints.fixed if block.category == "exercise" and block.start.date() == day]
        if fixed_workouts and any(block not in fixed_workouts for block in workouts):
            issues.append(f"Additional exercise on class day: {day}")
        if not fixed_workouts:
            minutes = sum((block.end - block.start).total_seconds() / 60 for block in workouts)
            if minutes > constraints.exercise_minutes_per_day:
                issues.append(f"Exercise exceeds requested duration: {day}")
    return issues
