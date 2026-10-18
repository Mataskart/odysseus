import json
import re


READ_TOOLS = frozenset({"read_file", "grep", "glob", "find_tools"})
TRANSIENT_ERROR = re.compile(
    r"timed?\s*out|timeout|temporar|rate.?limit|try again|connection|unavailable|busy|interrupted|\b(?:429|503)\b",
    re.IGNORECASE,
)


def _read_failure_kind(tool_name, result):
    if tool_name not in READ_TOOLS:
        return None
    if result.get("approval_required") or result.get("ask_user") or result.get("blocked"):
        return None
    failed = bool(result.get("error")) or result.get("exit_code") not in (None, 0)
    if failed:
        error = " ".join(str(result.get(key) or "") for key in ("error", "stderr", "output"))
        if TRANSIENT_ERROR.search(error):
            return None
        if re.search(r"permission denied|access denied|operation not permitted", error, re.I):
            return "permission_denied"
        if re.search(r"not found|no such file|does not exist", error, re.I):
            return "not_found"
        return "error"
    if tool_name == "find_tools" and result.get("discovered_tools") == []:
        return "empty"
    for key in ("matches", "results", "tools"):
        if result.get(key) == []:
            return "empty"
    output = str(result.get("output") or "").strip()
    if tool_name == "grep" and output.lower().startswith("no matches"):
        return "empty"
    if tool_name == "glob" and output.lower().startswith("no files matching"):
        return "empty"
    return None


class RepeatedReadGuard:
    def __init__(self):
        self.failures = {}
        self.stop = None

    def observe(self, tool_name, content, result):
        kind = _read_failure_kind(tool_name, result)
        if kind is None:
            if not result.get("error") and result.get("exit_code") in (None, 0):
                self.failures.clear()
                self.stop = None
            return
        content = (content or "").strip()
        try:
            arguments = json.loads(content)
        except (ValueError, TypeError):
            arguments = {"path": content} if tool_name == "read_file" else content
        if tool_name == "read_file" and isinstance(arguments, dict):
            arguments = {key: value for key, value in arguments.items()
                         if key not in {"offset", "limit"} or value not in (None, 0)}
        signature = (
            tool_name,
            json.dumps(arguments, sort_keys=True, ensure_ascii=False),
            json.dumps(result, sort_keys=True, ensure_ascii=False),
        )
        self.failures[signature] = self.failures.get(signature, 0) + 1
        if self.failures[signature] >= 2:
            self.stop = (tool_name, kind)

    def final_answer(self, user_text):
        tool_name, kind = self.stop
        lithuanian = re.search(
            r"[ąčęėįšųūž]|\b(?:perskaityk|faila[si]?|surask|pateik|patikrink)\b", user_text, re.I,
        )
        if lithuanian:
            reason = {"not_found": "šaltinis nerastas", "permission_denied": "prieiga uždrausta",
                      "empty": "nieko nerasta", "error": "įvyko klaida"}[kind]
            return (f"Sustojau, nes ta pati {tool_name} užklausa dukart grąžino tą patį rezultatą: {reason}. "
                    "Pateik pataisytą šaltinį arba trūkstamą informaciją.")
        reason = {"not_found": "the source was not found", "permission_denied": "access was denied",
                  "empty": "no matches were found", "error": "the call failed"}[kind]
        return (f"I stopped because the same {tool_name} call returned the same result twice: {reason}. "
                "Please provide a corrected source or the missing information.")
