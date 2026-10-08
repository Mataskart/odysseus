"""Detect psychology and study questions that should search notes and the web."""

import re

_STUDY_QUESTION = re.compile(
    r"\b(psycholog\w*|moodle|lectures?|textbooks?|coursework|"
    r"midterms?|exams?|flashcards?|apa style|peer[- ]reviewed|"
    r"journal articles?|study notes)\b"
    r"|\b(help me (?:study|revise)|quiz me on)\b"
    r"|\b(?:what is|explain|define|describe)\b.{0,80}\b(?:"
    r"conditioning|cognitive|behaviour\w*|behavior\w*|freud|piaget|"
    r"attachment|neuron\w*|synapse\w*|heuristic|dsm-?\d*|psychotherapy)\b"
    r"|\b(classical conditioning|operant conditioning|attachment theory)\b",
    re.IGNORECASE,
)


def looks_like_study_question(text: str) -> bool:
    return bool(_STUDY_QUESTION.search(str(text or "")))
