# Study-chat failures: implementation handoff

Prepared October 20, 2026. Repository: `/home/matas/odysseus`.

## Objective and scope

Fix the failures encountered by the user's SO while using the Odysseus client for study planning and searching indexed course material. The investigation was read-only; this handoff is the only file it added. The user intends another agent to implement the fixes.

Required outcomes:

1. Chat document retrieval recovers after RAG is unavailable at startup and reports unavailable retrieval honestly.
2. An assistant cannot silently finish an actionable request with an unsupported promise to search, including Lithuanian promises.
3. Follow-ups retain the unresolved document-search task and its relevant capabilities.
4. Review flags identify the exact persisted reply and can be correlated with turn diagnostics.
5. Requested versus actual model identity, effective sampling, and retrieval outcomes are diagnosable.
6. Validate planning constraint adherence separately from successful tool execution; do not claim that retrieving documents alone fixes schedule quality.

Do not retrain, export or replace models, rent a GPU, change the user's model launch configuration, push commits, or feed this private conversation into training. Preserve the transcript as a regression case, separate from training data. Do not send messages or write calendar events as part of replay validation. Any live reproduction should use an isolated test session and read-only retrieval.

## Existing work: preserve and integrate

The checkout is already dirty. Inspect the current diff before editing; do not reset, overwrite, or claim existing work as yours. Snapshot at handoff creation:

```text
 M local_finetune/RUNBOOK.md
 M local_finetune/setup_remote.sh
 M local_finetune/train_lora.py
 M specs/documents-rag-uploads.md
 M src/agent_loop.py
 M src/agent_tools/__init__.py
 M src/rag_vector.py
 M src/settings.py
 M src/tool_capabilities.py
 M src/tool_execution.py
 M src/tool_index.py
 M src/tool_policy.py
 M src/tool_schemas.py
 M src/tool_security.py
 M static/js/chat.js
 M tests/helpers/embedding_lanes.py
 M tests/test_agent_rounds_exhausted.py
 M tests/test_external_context_tool_gate.py
 M tests/test_foreground_model_routing.py
 M tests/test_local_tool_stall.py
?? specs/tool-discovery.md
?? src/tools/discovery.py
?? src/tools/knowledge.py
?? tests/test_chat_preparation_spinner_js.py
?? tests/test_knowledge_tool.py
?? tests/test_rag_shared_documents.py
?? tests/test_tool_discovery.py
```

HEAD was `ee5fdf1f` (October 18, recover malformed local tool calls), preceded by `c375c2c2` (October 18, Qwen XML calls and repeated-read stopping). Current code is newer than the October 17 incident. Historical logs establish the incident; current source establishes remaining defects. Do not assume today's tree exactly matches the process running during the incident.

Existing uncommitted changes add `search_knowledge`, recoverable `find_tools`, source guidance, discovery activation for subsequent rounds, and shared-document handling. Read `specs/tool-discovery.md`, `src/tools/discovery.py`, `src/tools/knowledge.py`, and their tests. These are useful prerequisites but do not solve promise-only responses: the model must still call them.

## Incident identity and evidence

- Session: `3ca5ca2b-5c3e-43eb-9043-5249b4f09666`, title `A Friendly Hello`, mode `agent`.
- SQLite: `data/app.db`, tables `sessions` and `chat_messages`. Open read-only while investigating, e.g. `sqlite3.connect('file:data/app.db?mode=ro', uri=True)`.
- Turn records: `/home/matas/.local/state/odysseus/turn-logs/turns.jsonl`, lines 100–103 at investigation time.
- Flags: `/home/matas/.local/state/odysseus/turn-logs/flags.jsonl`, lines 7–10 at investigation time.
- Application log: `data/logs/app.log`, incident around lines 14699–14866. Search by session ID, timestamp and quoted user text rather than relying on line numbers after edits/rotation.
- Application timestamps below are Vilnius local time (UTC+3); turn/flag JSON timestamps are UTC.

| User text | Completion time October 17 | Assistant message ID | Result |
|---|---|---|---|
| `pasiek visus mana failus ir rask visu atsiskaitymu datas` | 20:24:03 | `f22459b7-fbe5-4146-9596-3965674a23aa` | `Pažiūrėsiu į tavo failus ir rasiu atsiskaitymų datas.` |
| `continue` | 20:25:46 | `6336ac75-189e-4fa0-86ab-436cff94a604` | `Pažiūrėsiu į tavo failus ir rasiu visus atsiskaitymų datas. Pradėsiu nuo namų aplanko.` |
| `did you find?` | 20:27:01 | `f0154365-0a84-4c91-9183-273cba9403fe` | `Ieškau tavo failų — pažiūrėsiu namų aplanką ir rasiu atsiskaitymų datas.` |
| `HELLOOOOO check` | 20:37:07 | `4319ff7d-e2ca-4365-9ddc-0afc41d50e50` | `Čia esu! 👋 Kaip galiu padėti?` |

All four recorded one round, `finish_reason: stop`, no native tool calls, no parsed tool blocks, and no tool events. HTTP completions returned 200. There is no recorded execution failure or evidence of a swallowed tool result: no tool ran. All four recorded prompts retain the prior conversation, including the document-search request on later turns. No study-document passages were injected. Do not diagnose this as context overflow or the earlier `No user query found in messages` issue.

The user cancelled a preceding response to `its already 20:18 pm today and I will have to run later also`. There was also an edited first attempt with `failas` before `failus`. The completed four failures are independently logged after that edit; cancellation does not by itself explain them.

## A. Document RAG initialization and silent skipping

Evidence:

- `data/logs/app.log:14013`: October 17 14:19:45, `Vector document RAG not available at startup (ChromaDB may not be reachable yet — routes will retry lazily)`.
- Similar startup message at 10:44. The 14:19 process is the relevant later startup.
- Startup loads seven indexed directories and refreshes 288 documents from eight directories. A directory/file inventory does not establish that chat retrieval has a usable manager.
- `app.py` around 570 calls `get_rag_manager()` and passes the result into `initialize_managers`.
- `src/app_initializer.py` around 84 passes this value into `PersonalDocsManager`; `src/personal_docs.py` around 281 stores it as `self.rag_manager`.
- `src/chat_processor.py` around 405–439 obtains that stored value and executes retrieval only under `if rag_manager:`. A startup `None` silently skips the entire block, without calling the lazy accessor or warning.
- `routes/personal_routes.py` has a separate `_rag()` accessor that calls `get_rag_manager()`, so routes can recover without repairing the reference used by chat. No reassignment to `personal_docs_manager.rag_manager` was found in the inspected source.
- The incident's Chroma collection `4511068a-99eb-4e8e-9e29-d48fbe81ad70` was the memory collection, established by startup re-embedding logs. `62c8d1e2-b713-4c77-904c-caf3bb12f886` was used by tool selection. Successful queries against those collections are not proof of document RAG working.

The stored session currently has `rag=0`, but the historical request's checkbox state was not logged. `static/js/chat.js` sends `use_rag=false` only when the checkbox is off; `routes/chat_helpers.py` defaults omitted `use_rag` to true, with other suppression conditions. Do not contradict the user's report that RAG was enabled based on the stored session bit. The stale-manager path would skip retrieval even when enabled.

Implementation:

- Resolve the current manager on the chat retrieval path, respecting lazy-init throttling and thread safety. Avoid a process-lifetime snapshot of availability. Consider other consumers of the startup snapshot, including health reporting, without unnecessarily broad refactoring.
- Distinguish `disabled`, `unavailable`, `no_matches`, `below_threshold`, and `retrieved` outcomes. Existing threshold is 0.35. Log result counts and effective enabled/suppressed state, without dumping private source text unnecessarily.
- Make unavailability visible when the user requested work depending on indexed sources. Do not invent dates or imply an ongoing search when no search can run.
- Preserve authenticated owner scoping and authorized shared sources. Verify that the SO can access intended study documents through the existing shared-directory policy. Do not bypass ownership by searching as an unrestricted user.
- Do not lower the relevance threshold globally to mask initialization or routing defects. Do not claim a top-k search proves that all assessment dates were found.

Acceptance checks: manager absent at startup then available; retrieval still unavailable; disabled checkbox; no matches; below-threshold matches; authorized shared sources versus another account's private sources; visible outcome and matching diagnostics.

## B. Promise-only replies bypass both guards

Current source:

- `src/agent_loop.py`: `_TOOL_NARRATION_RE`, `_is_tool_narration_only`, `_is_local_tool_stall` around 2280; local retry around 5460.
- `_INTENT_RE` around 4628 and intent-without-action supervisor around 5748.
- Both recognizers match English constructions. Current history sanitization also uses `_is_tool_narration_only`.

Verification already performed: AST-extracted current functions/regexes were executed in isolation, without importing or modifying application state. Each of the three Lithuanian promises returned false from both recognizers; `I'll search your files.` returned true from both. The historical turn logs contain no recovery round.

Implementation:

- Cover Lithuanian, including accented/unaccented forms relevant to the incident. However, do not make an ever-growing list of English/Lithuanian phrases the entire correctness mechanism.
- Use an explicitly unresolved action plus execution/retrieval evidence to help detect a premature final. Distinguish a real answer, legitimate clarification, refusal/limitation, and plain conversation from an unsupported announcement.
- Coordinate the two existing recovery paths so retries have a clear finite budget. On exhaustion, return and persist an honest failure state visible in the UI, not another promise or a success-looking greeting.
- Ensure streamed narration, retried rounds, saved final content, and reloaded history agree. Existing text may already have reached the UI before a retry; avoid duplicated or misleading final text.
- Do not use unconditional `tool_choice=required` on every user message or auto-execute arbitrary guessed calls. Preserve normal authorization and tool policy.

Acceptance checks: the exact three promises; comparable English phrasing; a substantive answer containing `I'll`; a genuine clarification question; no available/authorized tool; a successful recovery call; repeated promise exhausting the cap; no tool retry after an already sufficient answer.

## C. Follow-up selection loses the unresolved task

Historical selection:

- Initial Lithuanian request: `low_signal=True`, `continuation=False`, `domains=[]`. `search_knowledge` WAS in the 12 native tools actually offered, along with file tools and `find_tools`. Missing-tool selection alone does not explain the first failure.
- `continue`: recognized continuation; query included the Lithuanian request and the earlier evening-run message. Selected 13 tools, including model-serving/calendar/task tools, but not document search/file-reading tools.
- `did you find?`: not recognized as continuation; selected 41 tools, many browser tools, although `search_knowledge` was present.
- `HELLOOOOO check`: not recognized as continuation; selected 13 mostly unrelated tools and omitted document search.

Inspect `_classify_agent_request`, `_is_explicit_continuation`, `_is_contextual_retry_continuation`, `_is_casual_low_signal`, `_recent_context_for_retrieval`, and tool-selection/domain pruning in `src/agent_loop.py`; also `src/tool_index.py`. Current retry continuation is narrowly Cookbook-oriented; casual greeting handling can discard contextual intent.

Implementation:

- Resolve short progress checks against an unresolved task, retaining its objective and required permitted capabilities. Avoid relying only on the last utterance's keywords or concatenating arbitrary recent turns.
- Keep document search and discoverability available for pending indexed-document work. Integrate with existing discovery changes; do not duplicate a separate tool catalog.
- A new unrelated topic or an actual completed task must stop this inheritance. Mere greetings must not revive old model-serving, email, or document actions.
- If introducing pending-task state, scope it to the session, distinguish cancel-current-generation from cancel-task, and define clearing/completion behavior. Do not let a previous promise count as successful execution.

Acceptance checks: exact four-turn sequence; Lithuanian initial request; `continue`; `did you find?`; frustrated follow-up; unrelated greeting after completion; explicit task cancellation/topic switch; unavailable/disabled tools.

## D. Flagging loses reply identity and reports misleading success

The four flags were written October 20 at 19:17:46, 19:17:48, 19:17:53 and 19:17:58 UTC (22:17 local). Each contains the session ID above and `message_id: ""`. Do not invent which flag timestamp maps to which reply; IDs above were recovered independently by matching saved content.

Trace:

- `static/js/chatRenderer.js`, `createMsgFooter`, around 1760: reads `msgElement.dataset.dbId || ''`, POSTs to `/api/turns/flag`, and marks success based only on `res.ok`.
- `routes/history/history_routes.py`, `_db_history_entry` around 130: serializes role/content/metadata but omits `m.id` / metadata `_db_id`.
- Paginated history uses that serializer around 150–190. `static/js/sessions.js` requests paginated history and forwards metadata; renderer expects `metadata._db_id`.
- `core/session_manager.py` adds `_db_id` to in-memory metadata AFTER the DB commit. Therefore the persisted metadata normally lacks it; loading raw DB rows requires explicitly restoring the ID.
- AST-isolated serializer reproduction with a row whose ID is `real-message-id` yielded no `_db_id`, confirming the current defect.
- `/api/turns/flag` around 849 accepts empty IDs and returns `{ok: true, recorded: ...}`.
- `src/turn_log.py` gates flags on turn logging being enabled and asynchronously appends to `flags.jsonl`. `record_flag` returning true means queued, not verified durable write. The UI ignores `recorded`; HTTP 200 with `recorded:false` still shows a checkmark.
- Search found the flags file writer but no automatic review worker consuming it. It is a local review marker, not an external review submission.
- `turns.jsonl` currently records session, model, messages, tools and rounds, but no stable reply/turn ID directly joinable to a flag.

Implementation:

- Return stable DB message IDs in all history paths (including pagination, archive/fallback, and messages with no metadata). Preserve them through live save and multi-round rendering.
- Validate session ownership and assistant-message membership in the flag route; reject missing or mismatched identifiers. Reuse established access checks.
- UI must inspect the response body and distinguish saved, logging disabled/unavailable, and failure. Avoid claiming durable storage merely because an async write was queued; choose explicit semantics.
- Correlate turn diagnostics and persisted messages using a stable turn ID or equivalent mapping. Account for retries, cancellation, edited/regenerated responses and multiple streamed rounds.
- Preserve existing blank-ID records; no destructive rewrite or fabricated mapping. Decide whether repeated flags should be idempotent.

Acceptance checks: flag live reply; reload then flag; paginated older reply; archive/history path; multi-round reply; no metadata; disabled logging; failed write; unauthorized or mismatched session/message; direct join from a new flag to its diagnostic turn.

## E. Model identity and effective sampling

The user ran `Qwen3.8-35B-A3B-Odysseus-v2-imatrix-Q4_K_M.gguf` from snapshot `e0d5ead39527aad64f140263da01f244b49a1ca4`, endpoint localhost:8000. Saved assistant metadata confirms this exact v2 model in `model` and `round_models` for all four failures.

The requested/session/turn-log model was instead the older empero-ai `Qwen3.8-35B-A3B-Q4_K_M.gguf`, snapshot `b1f9d1dcc3de8aa867669b0ab919384aeeb9b8d5`. Do not conclude the user ran the wrong model from the requested-model log. Capture requested and actual identities separately in correlated diagnostics.

User launch settings: CUDA device 0; `-ngl 99 -c 50048 --n-cpu-moe 33 --flash-attn on --cache-type-k q4_0 --cache-type-v q4_0 --parallel 1 --batch-size 2048 --ubatch-size 512 -t 8 --jinja --temp 0.6 --top-p 0.95 --top-k 20 --min-p 0 --presence-penalty 1.0`. Runtime slots reported context 50176. Saved input usage for the failures was about 11.8k–17.1k tokens, well below that limit.

Application log reports `Preset None: temp=1.0, max_tokens=0`. The request path explicitly passes temperature, overriding the llama-server default. `_is_odysseus_qwen_model` recognizes strings starting with `odysseus-qwen3`, not these absolute GGUF paths; do not blindly extend its specialized behaviors or impose its 0.2 cap on this model. Inspect effective request sampling and make it observable; distinguish app overrides from backend defaults. A controlled comparison may be useful, but sampling causation was not established and no live generation replay was done during investigation.

## F. Planning errors need separate validation

Original planning constraints: October 17, 2026; swimming Tue/Thu 19:30–21:30; running class Wed 18:00–20:00; one hour exercise on other days; easier sex-psychology exam October 22; difficult clinical-psychology exam October 24; two-page clinical research paper due Thursday October 22, not started and needing a few hours; bachelor's thesis plan by end of next week; Friday morning busy with brother; Wednesday classes 09:00–11:30 then 30-minute drive home, and 16:00–16:45; wake 08:00 weekdays except Thu 07:00, weekends 09:00; sleep 23:00; ask follow-ups one at a time. Later: tomorrow's 5k 11:00–12:00 then walk home; today already 20:18 and still needs a run.

The assistant claimed enough information without asking exam times. It labeled exam days but allocated no exam blocks. It claimed the paper was scheduled Friday evening (after Thursday's deadline), while the cited table slot was actually thesis work; its suggested Sunday slot also conflicted with the table. It invented class subjects and added extra exercise on swimming days. The later schedule update did not preserve the paper commitment.

Add a representative planning regression/check that tracks explicit constraints, preserves deadlines across revisions, flags missing exam/travel times as unknown, and does not schedule elapsed hours as future work. A structured constraint representation or validation pass may help; avoid a one-off hardcoded solution for this transcript or forcing tools on pure planning. Separate deterministic validation from stochastic model quality. Report any remaining limitations honestly.

## Validation and completion report

Read current repository/skill instructions, then implement focused changes while preserving unrelated work. Existing useful tests include `tests/test_local_tool_stall.py`, `tests/test_agent_rounds_exhausted.py`, `tests/test_foreground_model_routing.py`, `tests/test_knowledge_tool.py`, `tests/test_tool_discovery.py`, `tests/test_rag_shared_documents.py`, `tests/test_external_context_tool_gate.py`, and `tests/test_ui_control_rag_toggle.py`.

Use deterministic mocked-stream tests for routing/recovery/failure semantics and JS/API tests for flags. Then, if the local server and an appropriately scoped test session are available, replay the critical conversation and verify actual tool events plus returned source passages under the SO's access scope. No live model replay or actual document-search success was established by the investigation. If live validation is unavailable, state that rather than substituting unit-test success for production proof.

Completion report should list changes and relevant tests, demonstrate that a failed retrieval cannot masquerade as ongoing work, show a valid flag-to-turn correlation, distinguish requested/actual model and effective sampling, and explicitly report whether the planning and real-source retrieval checks passed. Do not claim every assessment date was recovered unless source coverage supports that claim.
