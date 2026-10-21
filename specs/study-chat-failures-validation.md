# Study-chat implementation and validation

October 20, 2026. Implements `study-chat-failures-handoff.md` on top of the existing discovery/shared-document work.

## Changes

- Chat resolves the lazy document manager for each retrieval, rather than retaining startup availability. Singleton initialization is serialized and failed attempts remain throttled. Health routes resolve the current manager in a worker thread.
- Retrieval records enabled state, result counts, threshold, and `disabled`, `unavailable`, `no_matches`, `below_threshold`, or `retrieved`. Strict error reporting prevents collection failures from masquerading as empty results; the existing keyword fallback remains available. Both chat and `search_knowledge` use the unchanged 0.35 threshold and authenticated owner/shared-source filtering. Explicitly disabling RAG also disables `search_knowledge` for the turn.
- Pending document work is reconstructed from the session's own history. Progress checks use that objective for retrieval and capability selection. Cancellation/topic changes and substantive completion end inheritance; greetings alone do not revive tasks. Cancelling a generation leaves the unresolved user request in history.
- English/Lithuanian announcements share one recovery budget: at most two nudges, bounded further by the round limit and available permitted tools. A pending document task also requires source evidence, a relevant clarification, or an explicit limitation, independently of promise wording. Rejected prose is buffered, excluded from the final response, and replaced with an honest failure on exhaustion. Empty round placeholders preserve model/endpoint alignment without restoring rejected promises on reload.
- History serialization restores the actual database message ID, including pagination/fallback and absent metadata. The live final round receives that ID. Flagging checks ownership and assistant-message membership. The UI checks `recorded` and `status`; `saved` means the flag write was flushed and fsynced. Repeated flags deliberately append separate review events. Existing blank-ID records are untouched.
- New assistant saves carry a turn ID. Opt-in persistence diagnostics map it to the exact message ID, including stopped replies. Agent diagnostics carry the same turn ID, requested/actual models, per-round sampling, and retrieval outcomes. The OpenAI-compatible stream reports actual sent sampling fields after payload normalization; unspecified fields are labeled backend defaults. GGUF paths do not acquire the specialized fine-tune temperature cap.
- Planning guidance preserves explicit constraints across revisions and asks for unknown exam/travel times. A separate structured validator/regression checks fixed commitments, overlaps, elapsed time, work duration/deadlines, exercise, wake/sleep windows, and missing times. It does not parse or certify arbitrary model-generated schedule prose.

## Deterministic validation

The combined 21-file suite passed **439 tests**. Subsequent focused suites passed **47 retrieval/recovery tests**, **47 embedding/approval/context tests**, and **38 final behavior/flag/planning tests**, plus a dedicated successful Lithuanian promise-to-source-tool recovery test. Counts overlap; they are not a summed unique total. `git diff --check` passed.

Key regression files:

- `tests/test_study_chat_retrieval.py`
- `tests/test_study_chat_recovery.py`
- `tests/test_study_planning_constraints.py`
- `tests/test_turn_review_identity.py`
- `tests/test_review_flag_js.py`
- `tests/test_llm_core_streaming.py`

Existing routing, local-stall, round-exhaustion, discovery, knowledge, shared-document, UI RAG toggle, history, streaming/fallback, and persistence tests were included. One existing provenance expectation now retains an empty placeholder instead of rejected promise text.

The flag integration test persists a reply with `turn_id=stable-turn`, obtains its database ID, flags it through the API, then reads both log files. It verifies matching turn IDs and matching flag/persistence message IDs, plus distinct requested `old.gguf` and actual `actual-v2.gguf` identities and sent temperature 1.0. Disabled logging, failed writes, foreign ownership, invalid membership, pagination, and metadata-free history are covered independently.

## Live checks and limits

The incident session's owner was verified read-only as `ugne`. The application and llama-server health endpoints responded successfully. Validation used isolated session identifiers, an in-memory validation database, disabled turn logging, no teacher escalation, and only the permitted `search_knowledge` tool. No messages/calendar actions were allowed. The incident session was not replayed or modified.

An initial standalone process lacked the app's `FASTEMBED_MODEL` environment and tried the default MiniLM model against a multilingual index. That validation process was stopped. Subsequent checks explicitly used the running app's verified configuration, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, and refused all collection creation/reset/migration during validation. The app/model launch configuration was unchanged.

With the matching configuration, direct owner-scoped retrieval returned five nonempty passages from real study PDFs. A one-round native-model replay emitted two `search_knowledge` calls with exit code 0: eight and six above-threshold source passages respectively. It emitted `rounds_exhausted`, rather than completing an assessment-date answer. A separate three-round replay also executed tools without completing the date inventory. These checks prove accessible source content and actual tool dispatch, not exhaustive date coverage or a finished answer.

A separate unavailable-retrieval replay exercised the four incident utterances. Its final generic Lithuanian greeting exposed a remaining guard gap; that exact reply became a regression case. Rechecking the frustrated follow-up after the fix returned: “I could not complete the requested search or action. No background work is running. Please retry or check source/tool availability.” The failure metadata reports the bounded recovery cap.

Deterministic planning checks passed. No live generated schedule was certified, and no claim is made that all assessment dates were recovered. The running application process was not restarted; live loop checks imported the edited source in isolated processes, rather than proving deployment through the existing HTTP process.

The prior training work and other unrelated edits were preserved. No retraining, model export/replacement, paid compute, push, or training-data ingestion was performed. Private replay output remains outside the repository; regression tests use only the small incident phrases and representative constraints.

## Follow-up review

The follow-up review found and corrected additional pending-task edge cases: explicit cancellation and how-to questions no longer create a document-search objective; retrieved context marked untrusted cannot replace the user's objective; object-based chat histories preserve pending-task metadata during retrieval preparation. The merged narration guard also retains recovery for English announcements such as “I need to inspect the logs.” Regression tests cover these cases.

The reviewer independently ran the initial focused suite (187 passed), the expanded routing/security/retrieval suite after fixes (306 passed), and the final history/persistence/context/retrieval suite on October 21 (107 passed). These counts overlap. The diagnostics route test now mocks the lazy manager accessor so it cannot initialize the real document index. Live model replay was not repeated, and the earlier limits on date coverage, generated schedule quality, and deployment remain applicable.
