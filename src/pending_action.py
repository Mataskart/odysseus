"""Resolve progress checks against unfinished indexed-source work in this history."""

import re
import unicodedata


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower()) if not unicodedata.combining(c))


def is_document_search(text):
    value = normalized(text)
    if re.search(
        r"\b(?:do not|don't|dont|stop|cancel|never)\b.{0,60}\b(?:search\w*|find\w*|read\w*|check\w*|access\w*)\b"
        r"|\b(?:neieskok|neieskoti|netikrink|neskaityk|nepasiek|atsauk)\b",
        value,
    ):
        return False
    if re.search(
        r"\b(?:how (?:do|can|should|would) (?:i|we)|how to|teach me|explain how|kaip (?:man|galeciau|galiu))\b",
        value,
    ):
        return False
    sources = re.search(r"\b(?:files?|documents?|indexed|course|moodle|fail\w*|dokument\w*|atsiskaitym\w*)\b", value)
    action = re.search(r"\b(?:search|find|read|check|access|look|rask|rasti|pasiek|ieskok|surask|perziurek)\b", value)
    return bool(sources and action)


def is_progress_check(text):
    value = normalized(text).strip(" .!?")
    return bool(re.fullmatch(
        r"(?:continue|carry on|did you find(?: it| anything)?|any (?:updates?|progress)|"
        r"are you done|check|hello+ check|tesk|ar radai|radai|ka radai)", value,
    ))


def is_promise(text):
    value = normalized(text).strip()
    if len(value) >= 400 or "```" in value or "?" in value:
        return False
    if re.search(r"\b(?:cannot|can't|unable|unavailable|disabled|nepasiekiam\w*|negaliu)\b", value):
        return False
    match = re.search(
        r"(?:^|[.!—–\n])\s*(?:paziuresiu|perziuresiu|ieskau|ieskosiu|rasiu|pradesiu)\b[^?]*$", value,
    )
    if not match:
        return False
    prefix = value[:match.start()]
    prefix = re.sub(r"\b(?:gerai|taip|pirmiausia|dabar)\b", "", prefix)
    return not bool(re.search(r"\w", prefix))


def pending_document_objective(messages, latest):
    objective = None
    for message in messages:
        metadata = message.get("metadata") or {}
        if message.get("_agent_injected") or message.get("_untrusted_context") or metadata.get("trusted") is False:
            continue
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str):
            continue
        if role == "user":
            if is_document_search(content):
                objective = content
            elif not is_progress_check(content):
                objective = None
        elif role == "assistant" and objective:
            if metadata.get("pending_objective"):
                continue
            if message.get("tool_calls") or is_promise(content) or is_progress_check(content):
                continue
            limitation = re.search(r"\b(?:unavailable|disabled|cannot access|could not complete|no matches|no relevant|not found|could not find|neradau|nerado|nepasiekiam\w*|negaliu pasiekti)\b", normalized(content))
            if "No background work is running" in content or limitation:
                continue
            # A substantive answer ends the task; a clarification retains it.
            if content.strip() and "?" not in content and not re.search(
                r"^(?:sure[,.!]?\s*|good idea[,.!—–]?\s*)?(?:I'll|I’ll|I will|let me)\b", content, re.IGNORECASE,
            ):
                objective = None
    if is_document_search(latest):
        return latest
    return objective if is_progress_check(latest) else None


def premature_document_reply(text, objective, has_evidence):
    if not objective or has_evidence:
        return False
    value = normalized(text).strip()
    if re.search(r"\b(?:cannot|can't|unable|unavailable|disabled|could not|no (?:access|matches|results|relevant)|won't|will not|nepasiekiam\w*|negaliu|nepavyko|neradau|nerado|atsisakau)\b", value):
        return False
    if "?" in value:
        generic_help = re.search(r"(?:kaip|kuo|how)\s+(?:galiu padeti|can i help)|anything else", value)
        task_detail = re.search(r"\b(?:which|where|files?|folders?|documents?|courses?|path|kuri\w*|kok\w*|fail\w*|aplank\w*|dokument\w*|kurs\w*|saltin\w*)\b", value)
        return bool(generic_help) or not bool(task_detail)
    return bool(value)
