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
    def __init__(self, user_text="", read_file_only=False):
        self.failures = {}
        self.stop = None
        self.empty_searches = []
        self.failed_attempts = 0
        self.retry_notice_sent = False
        self.redundant_search = False
        self.requested_source = None
        self.requested_source_failed = False
        if read_file_only:
            paths = {path.rstrip(".,;:!?)]}") for path in re.findall(r"(?<!\w)/[^\s<>'\"`]+", user_text)}
            sources = {path for path in paths
                       if not any(other.startswith(path.rstrip("/") + "/") for other in paths if other != path)}
            if len(sources) == 1:
                self.requested_source = sources.pop()

    def observe(self, tool_name, content, result):
        kind = _read_failure_kind(tool_name, result)
        if kind is None:
            if not result.get("error") and result.get("exit_code") in (None, 0):
                self.failures.clear()
                self.stop = None
                self.empty_searches.clear()
                self.failed_attempts = 0
                self.redundant_search = False
                self.requested_source_failed = False
            return
        if self.requested_source_failed:
            return
        self.failed_attempts += 1
        content = (content or "").strip()
        try:
            arguments = json.loads(content)
        except (ValueError, TypeError):
            arguments = {"path": content} if tool_name == "read_file" else content
        if (tool_name == "read_file" and isinstance(arguments, dict)
                and arguments.get("path") == self.requested_source
                and self.requested_source is not None
                and kind in {"not_found", "permission_denied"}):
            self.requested_source_failed = True
            self.stop = (tool_name, kind)
        if tool_name == "read_file" and isinstance(arguments, dict):
            for option in ("offset", "limit"):
                if kind in {"not_found", "permission_denied"} or arguments.get(option) in (None, 0):
                    arguments.pop(option, None)
        if tool_name == "grep" and kind == "empty" and isinstance(arguments, dict):
            arguments = {key: value for key, value in arguments.items()
                         if key not in {"max_results", "ignore_case"}}
            self._observe_empty_search(content)
        signature = (
            tool_name,
            json.dumps(arguments, sort_keys=True, ensure_ascii=False),
            json.dumps(result, sort_keys=True, ensure_ascii=False),
        )
        self.failures[signature] = self.failures.get(signature, 0) + 1
        if self.failures[signature] >= 2:
            self.stop = (tool_name, kind)

    def _observe_empty_search(self, content):
        try:
            arguments = json.loads(content)
        except (ValueError, TypeError):
            return
        pattern = arguments.get("pattern")
        if not isinstance(pattern, str) or not pattern or re.search(r"[.\[\](){}*+?|^$\\]", pattern):
            return
        scope = (arguments.get("path"), arguments.get("glob"))
        ignore_case = bool(arguments.get("ignore_case"))
        for previous_scope, previous_pattern, previous_ignore_case in self.empty_searches:
            if scope != previous_scope or (ignore_case and not previous_ignore_case):
                continue
            if previous_ignore_case:
                if not previous_pattern.isascii() or not pattern.isascii():
                    continue
                contained = previous_pattern.casefold() in pattern.casefold()
            else:
                contained = previous_pattern in pattern
            if contained:
                self.redundant_search = True
                self.stop = ("grep", "empty")
                return
        self.empty_searches.append((scope, pattern, ignore_case))

    def take_retry_notice(self):
        if self.failed_attempts < 3 or self.retry_notice_sent:
            return None
        self.retry_notice_sent = True
        return (
            "Three read/search/discovery attempts have returned no usable evidence. "
            "Do not keep guessing filenames or rephrasing an exhausted search. "
            "If there is a concrete untried correction or a different justified approach, use it. "
            "If the user requested multiple independent sources, continue checking the remaining sources. "
            "Otherwise finish now with the observed limitation and a useful next step; do not invent a result."
        )

    def final_answer(self, user_text):
        tool_name, kind = self.stop
        lithuanian = re.search(
            r"[ąčęėįšųūž]|\b(?:perskaityk|faila[si]?|surask|pateik|patikrink)\b", user_text, re.I,
        )
        if lithuanian:
            if self.requested_source_failed:
                reason = "šaltinis nerastas" if kind == "not_found" else "prieiga uždrausta"
                return (f"Nepavyko perskaityti nurodyto šaltinio: {reason}. "
                        "Pateik pataisytą kelią, leistiną kopiją arba failo turinį.")
            if self.redundant_search:
                return ("Sustojau, nes pakartotinė paieška jau patikrintoje srityje nieko nerado. "
                        "Pateik pataisytą šaltinį arba trūkstamą informaciją.")
            reason = {"not_found": "šaltinis nerastas", "permission_denied": "prieiga uždrausta",
                      "empty": "nieko nerasta", "error": "įvyko klaida"}[kind]
            return (f"Sustojau, nes ta pati {tool_name} užklausa dukart grąžino tą patį rezultatą: {reason}. "
                    "Pateik pataisytą šaltinį arba trūkstamą informaciją.")
        if self.requested_source_failed:
            reason = "the source was not found" if kind == "not_found" else "access was denied"
            return (f"I couldn't read the requested source: {reason}. "
                    "Please provide a corrected path, an authorized copy, or the file contents.")
        if self.redundant_search:
            return ("I stopped because another search within an already exhausted query returned no matches. "
                    "Please provide a corrected source or the missing information.")
        reason = {"not_found": "the source was not found", "permission_denied": "access was denied",
                  "empty": "no matches were found", "error": "the call failed"}[kind]
        return (f"I stopped because the same {tool_name} call returned the same result twice: {reason}. "
                "Please provide a corrected source or the missing information.")
