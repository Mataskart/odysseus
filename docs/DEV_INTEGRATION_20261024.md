# Dev integration preservation report — 2026-10-24

This is an isolated integration of the handoff's pinned dev snapshot. It is not a production cutover or publication. Both histories are retained; behavioral preservation is assessed separately through the ledger and validation below.

## Reproducible state

- Original branch: `local/tool-calling-fixes`, `6d791e39821532b663f1e932f383b89bbbcd0d18`.
- Target: `origin/dev`, pinned to `01566b158e627748f70ac402571f2f78241fb6f9`; no newer snapshot substituted.
- Merge base: `3b6c169162330cd35c4ce6d14949ef15fd3208a2`.
- Backup ref: `backup/pre-dev-integration-20261023`.
- Verified bundle: `/home/matas/odysseus-integration-backups/20261023/pre-dev.bundle`.
- Integration branch: `codex/dev-integration-20261023`.
- Worktree: `/home/matas/.codex/worktrees/dev-integration-20261023/odysseus`.
- Evidence directory: `/home/matas/odysseus-integration-backups/20261023/`.
- The merge commit containing this report has the original branch and target as its two parents. Its hash is supplied in the completion message to avoid a self-referential file.

## Conflict and clean-merge audit

The real diff3 merge had 31 conflicting files and 99 blocks. All were reconciled individually. The handoff's 90-block merge-tree preview used a different representation; it was not an executable validation result.

The main reconciliations were context grouping and Unicode budgeting; LLM reasoning/temperature/timing APIs; upstream tool registry relocation and authority; study retrieval/recovery; native dispatch; history/review IDs; frontend stage/stream contracts; Cookbook lifecycle; and picker route identity. Upstream native effect containment, explicit policy denials, route provenance, usage accounting, card disposal, timeout handling, and split styles/modules are retained.

Clean merges were audited through both parent diffs, not accepted solely because Git reported no conflict. The accompanying `DEV_INTEGRATION_20261024_FILES.tsv` inventories every path changed by our 29 commits. Exact branch matches are identified by Git blob comparison. Changed paths were reviewed with their surrounding integration points and exercised through the suites below. Upstream-only additions receive syntax, frontend and broad-suite coverage; this is not a claim of manual review of all 497 upstream commits.

Notable semantic fixes outside conflict markers:

- Strict Qwen parsing is shared by upstream's fallback parser, including declared environment tool names. A second parser cannot guess a name or reaccept malformed arguments.
- Indexed knowledge and optional judgment tools participate in upstream request authority. Generic workspace files and established follow-ups retain upstream routing. Discovery grants no execution authority for its results.
- Forced tool selection survives route rebuilding and web schema filtering, but explicit caller and policy denials still win.
- Deferred heavy tools stay filtered after schema enrichment; explicit forced/declared tools remain usable.
- Recovery works for textual-tool routes as well as native schemas; disabled tool sets do not trigger futile retries.
- Injected user-role diagnostics cannot displace the latest real user request during trimming; Unicode estimates apply to multipart text too.
- Cookbook test fixtures now stub the upstream timeout wrapper, and picker fixtures include the real route-identity helper. Single-tool read-guard fixtures explicitly disable unrelated upstream tools. Assertions were retained; no failing tests were deleted.
- `.dockerignore` now excludes the entire local training workspace, closing the narrower parent exclusion of only `seed_chats`.
- Native Qwen GGUF filenames containing “Odysseus” do not implicitly opt into upstream's compact tool router, forced sampling, or output cap. The v2 path retains native tool schemas and the requested temperature/token limit; upstream named router profiles remain supported.
- Successful discovery extends the active turn's offered schemas only within its policy inventory. Request authority remains unchanged, so discovering a tool cannot authorize its execution.
- Teacher recovery carries the original request separately from diagnostic prose, avoiding false document objectives. External declared-tool routes retain their authoritative system contract ahead of local runtime guidance.
- At the round cap, a web-search promise yields to upstream's evidence-based final synthesizer. Study requests without evidence still receive the branch's bounded failure response.
- Declared direct XML calls now strip their exact spans while retaining surrounding prose; this also fixes an upstream undefined-helper path reached during parser integration. Qualified email XML names preserve typed arguments.
- Offline service-worker precaching retains one versioned panels-loader identity and adds the local-startup module. Browser fixtures navigate to that same deployed identity and still exercise fresh offline imports. Generated configuration reference now documents the branch's default-off turn logging settings.
- Changed upstream test expectations distinguish native bash from TUI host-shell tools, local data from external approval triggers, and the added read-only discovery schema. Frontend assertions follow the retained route helper, response-timeout handler, and rAF scroll behavior; behavioral assertions remain in place.

Additional integration edits outside the branch-path ledger: `scripts/generate_env_reference.py`, `src/agent_runtime/authority.py`, `src/model_profiles.py`, `src/teacher_escalation.py`, `src/tool_types.py`, `src/turn_contract.py`, `tests/browser/notesOffline.mjs`, `tests/test_agent_runtime_context.py`, `tests/test_api_token_tool_authority.py`, `tests/test_clean_agent_preview.py`, `tests/test_dev_integration_contracts.py`, `tests/test_frontend_foundation_offline_js.py`, `tests/test_model_name_tooltip.py`, `tests/test_pr6020_browser_review_regressions.py`, `tests/test_product_turn_contract_route.py`, `tests/test_request_authority.py`, `tests/test_stream_completion_scroll_stability.py`, `tests/test_tls_overrides_scope.py`, `website/configuration-reference.md`. These reconcile upstream authority/model/runtime APIs, generated documentation, and test fixtures with the retained branch behavior.

## Commit-by-commit preservation ledger

Evidence names below are test modules under `tests/` unless marked otherwise. Aggregate results and limitations are recorded in Validation; a named test is not a live-model claim.

### `736ec660` — Keep bash/python available when the intent classifier misses a shell request

- Files: `src/agent_loop.py`, `tests/test_bg_job_tools.py`, `tests/test_workspace_confine.py`.
- Resolution: Kept native bash/python fallback and explicit tool selection through heuristic route rebuilding, while policy denials remain final. Upstream native execution stays contained.
- Evidence: test_runtime_retry_progress.py; test_bg_job_tools.py; test_workspace_confine.py; test_native_execution_containment.py.

### `48a92be5` — Don't arm the external-context approval gate on local tool output

- Files: `src/tool_capabilities.py`, `tests/test_external_context_tool_gate.py`.
- Resolution: Kept WORKSPACE_UNTRUSTED results from arming the external-context gate. Upstream request-scoped authority, action authorization and external-context policy still apply.
- Evidence: test_external_context_tool_gate.py; test_tool_approval*.py; test_request_authority.py.

### `1258c89b` — Cookbook: pass sibling mtp-*.gguf drafter as --model-draft when MTP Spec is on

- Files: `routes/cookbook_helpers.py`, `static/js/cookbook.js`, `static/js/cookbookServe.js`.
- Resolution: Kept mtp-*.gguf classification, separate sibling drafter command generation and avoidance of drafter/projector as primary model.
- Evidence: test_cookbook_drafter_selection_js.py; test_cookbook_helpers.py.

### `b5d77540` — Cookbook: prefer repo-root MTP drafter over subfolder alternates

- Files: `static/js/cookbookServe.js`.
- Resolution: Kept repository-root MTP drafter preference over subfolder alternates, and same-snapshot filtering.
- Evidence: test_cookbook_drafter_selection_js.py.

### `e5d2049f` — Make local models act inside Odysseus instead of refusing tools.

- Files: `routes/chat_helpers.py`, `routes/chat_routes.py`, `routes/history/history_routes.py`, `src/agent_loop.py`, `src/chat_processor.py`, `src/prompt_security.py`, `src/settings.py`, `src/study_intent.py`, `src/tool_schemas.py`, `src/turn_log.py`, `static/js/chatRenderer.js`.
- Resolution: Kept local action/runtime note, study intent, Qwen prompt/schema guidance, metadata and local review logging. Upstream request authority and effect containment remain enforcement boundaries.
- Evidence: test_local_tool_stall.py; test_study*.py; test_foreground_model_routing.py; test_request_authority.py; test_tool_approval*.py.

### `d470b86a` — Add local LoRA prep so a rented GPU session can start from checked data.

- Files: `local_finetune/RUNBOOK.md`, `local_finetune/check_template.py`, `local_finetune/eval_prompts.jsonl`, `local_finetune/seed_tasks.jsonl`, `local_finetune/setup_remote.sh`, `local_finetune/teacher_prompt.txt`, `local_finetune/train_lora.py`, `local_finetune/validate_dataset.py`.
- Resolution: Preserved all tracked local preparation files exactly. No datasets, evaluations, model weights or training recipes were executed or modified.
- Evidence: Tracked-file object comparison; three protected SHA256 checks.

### `89e82720` — Skip turn logging under pytest and update the backup-route prompt assertion.

- Files: `src/turn_log.py`, `tests/test_foreground_model_routing.py`.
- Resolution: Kept pytest turn-log suppression and default-off production logging; preserved suffix assertions and upstream route provenance checks.
- Evidence: test_turn_review_identity.py; test_foreground_model_routing.py; turn_log.py byte comparison.

### `79c5afa3` — Hide pipeline, research and teacher tools unless the request asks for them.

- Files: `src/agent_loop.py`, `tests/test_foreground_model_routing.py`.
- Resolution: Kept deferred research/pipeline/teacher selection. Reapplied it after upstream schema enrichment; explicitly forced tools and declared environment tools remain eligible subject to authorization.
- Evidence: test_dev_integration_contracts.py; test_foreground_model_routing.py.

### `a5354dbe` — Match backup-route prompts by suffix now that a runtime note is prepended.

- Files: `tests/test_foreground_model_routing.py`.
- Resolution: Kept backup-route prompt suffix assertions to accommodate the runtime note without accepting the primary-route prompt on fallback.
- Evidence: test_foreground_model_routing.py.

### `8f444b52` — Keep local skill listings from arming the tool gate, and index Word course notes.

- Files: `src/chat_processor.py`, `src/personal_docs.py`, `src/rag_vector.py`.
- Resolution: Kept local skill/memory/RAG context from arming the external-context gate, with external sources still gated. Kept Word extraction fallback and added upstream legacy .doc extraction.
- Evidence: test_external_context_tool_gate.py; test_personal_docs_keyword_fallback.py; test_legacy_word_reader.py; test_rag_shared_documents.py.

### `c5ef7bbb` — Make /rag on turn course search on instead of listing an empty folder registry.

- Files: `src/personal_docs.py`, `static/js/chat.js`, `static/js/slashCommands.js`.
- Resolution: Retained /rag on and /rag off as course-search toggle commands, distinct from registry listing; kept names-only startup catalog and lazy keyword extraction.
- Evidence: test_ui_control_rag_toggle.py; test_personal_docs_keyword_fallback.py; slashCommands.js audit.

### `c7b6f07b` — Load the /rag on command on the next page reload.

- Files: `src/personal_docs.py`, `static/app.js`, `static/index.html`, `static/sw.js`.
- Resolution: Retained command/module cache invalidation; service-worker cache advanced to odysseus-v660-dev-integration rather than reusing either parent cache.
- Evidence: frontend module/version checks; static/sw.js audit.

### `e7fecdd0` — Put a RAG toggle next to the web search icon.

- Files: `static/app.js`, `static/index.html`, `static/js/compare/index.js`, `static/sw.js`.
- Resolution: Kept toolbar RAG toggle, state synchronization and compare-mode hiding; integrated upstream index/style/module versions.
- Evidence: test_ui_control_rag_toggle.py; test_chat_preparation_spinner_js.py; frontend checks.

### `63fce77b` — Preserve Cookbook launch panel when reopening

- Files: `static/js/cookbook.js`, `static/js/cookbookServe.js`.
- Resolution: Kept in-memory unlaunched Cookbook draft capture/restoration across reopening, combined with upstream immediate shell paint and background synchronization.
- Evidence: test_cookbook_inventory_regressions.py; test_cookbook*.py.

### `0a75880d` — Remove mobile plan swipe placeholder

- Files: `static/app.js`.
- Resolution: Removed the mobile swipe placeholder timer and hint as intended; kept upstream responsive composer logic.
- Evidence: static/app.js diff audit; JS syntax; frontend tests.

### `f5c5f31f` — Improve chat tool recovery and stream follow

- Files: `src/agent_loop.py`, `src/llm_core.py`, `src/turn_log.py`, `static/js/chat.js`, `static/js/ui.js`, `tests/test_local_tool_stall.py`.
- Resolution: Kept bounded promise recovery, stall reporting and rAF stream-follow with user-scroll pause/resume. Retained upstream scroll snapshot/restore and prevented duplicate buffered prose emission.
- Evidence: test_local_tool_stall.py; test_agent_rounds_exhausted.py; test_stream_completion_scroll_stability.py; test_ui_visibility_js.py.

### `8b683ced` — Show staged chat startup progress

- Files: `static/js/chat.js`.
- Resolution: Kept context/model preparation stage messages. Startup waits finish before the chat response timeout starts; upstream between-round waiting behavior remains.
- Evidence: test_chat_preparation_spinner_js.py; test_local_model_startup.py.

### `4b935204` — Expose chat startup timing breakdown

- Files: `routes/chat_routes.py`, `src/agent_loop.py`, `src/llm_core.py`, `static/js/chatRenderer.js`.
- Resolution: Kept startup callbacks across agent and direct LLM paths and detailed first-token timings in upstream metric layout; retained upstream usage/cost and route attribution.
- Evidence: test_llm_core_streaming.py; test_chat_preparation_spinner_js.py; test_foreground_model_routing.py.

### `186badd0` — Default Qwen to temperature 0.6 and disable thinking for search queries

- Files: `routes/chat_helpers.py`, `routes/chat_routes.py`, `src/chat_handler.py`, `src/chat_processor.py`, `src/constants.py`, `src/llm_core.py`, `tests/test_qwen_sampling_defaults.py`.
- Resolution: Kept Qwen temperature 0.6 only when presets do not explicitly set it, plus search-query thinking=False. PresetInfo also retains upstream persona-memory fields; LLM APIs retain thinking_mode/reasoning_effort.
- Evidence: test_qwen_sampling_defaults.py; test_llm_core*.py.

### `34b172b5` — Fix review findings in search, chat context, tool routing and Cookbook

- Files: `local_finetune/validate_dataset.py`, `routes/chat_helpers.py`, `routes/history/history_routes.py`, `services/search/core.py`, `services/search/providers.py`, `src/action_intents.py`, `src/agent_loop.py`, `src/chat_processor.py`, `src/llm_core.py`, `src/personal_docs.py`, `src/turn_log.py`, `static/app.js`, `static/index.html`, `static/js/chat.js`, `static/js/chatRenderer.js`, `static/js/compare/index.js`, `static/js/compare/stream.js`, `static/js/cookbook.js`, `static/js/cookbookServe.js`, `static/js/ui.js`, `static/sw.js`, `tests/test_brave_search_request.py`, `tests/test_chat_processor_web_search.py`, `tests/test_cookbook_cpu_only_serve.py`, `tests/test_cookbook_drafter_selection_js.py`, `tests/test_external_context_tool_gate.py`, `tests/test_local_tool_stall.py`, `tests/test_personal_docs_keyword_fallback.py`, `tests/test_token_cache_atomic_swap.py`, `tests/test_tool_approval_frontend_routing.py`, `tests/test_tool_approval_task_scope.py`.
- Resolution: Kept Brave raw queries/freshness/rate-limit fallback, per-thread context state, follow-up query generation, local-context gate exceptions, keyword document fallback, CPU-only serve and MTP behavior. Combined upstream empty-provider fallback and native dispatch.
- Evidence: test_brave_search_request.py; test_chat_processor_web_search.py; test_personal_docs_keyword_fallback.py; test_external_context_tool_gate.py; test_cookbook*.py; test_token_cache_atomic_swap.py.

### `5a515409` — Add optional OpenJev judgment tool

- Files: `specs/openjev.md`, `src/action_intents.py`, `src/agent_loop.py`, `src/agent_tools/__init__.py`, `src/settings.py`, `src/tool_capabilities.py`, `src/tool_index.py`, `src/tool_policy.py`, `src/tool_schemas.py`, `src/tool_security.py`, `src/tools/openjev.py`, `tests/test_openjev_tool.py`.
- Resolution: Kept optional local advisory OpenJev, bounded payload/schema/timeouts, disabled default and no cloud fallback. Registered judgment authority without replacing established web/workspace follow-up capabilities. Direct execution tests supply upstream-required authority.
- Evidence: test_openjev_tool.py; test_request_authority.py; test_turn_contract.py; test_dev_integration_contracts.py.

### `e51dabb0` — Fail clearly when required context cannot fit

- Files: `src/agent_loop.py`, `src/context_compactor.py`, `tests/test_context_tool_loop_trimming.py`, `tests/test_foreground_model_routing.py`.
- Resolution: Kept ContextBudgetError when required context cannot fit, clear stream errors and fallback-route recovery. Combined branch exchange grouping with upstream Unicode estimator and real-user provenance checks.
- Evidence: test_context*.py; test_foreground_model_routing.py; test_dev_integration_contracts.py.

### `348a0b4b` — Keep the local fine-tuning workspace out of git and Docker

- Files: `.dockerignore`, `.gitignore`.
- Resolution: Retained Git exclusion of the local fine-tuning workspace. Expanded Docker exclusion from seed_chats to the entire local_finetune directory as required by this handoff, preserving upstream distribution notice inclusions.
- Evidence: Git ignore inspection; protected-file hashes; no Docker build.

### `c375c2c2` — Handle Qwen XML tool calls and stop repeated read failures

- Files: `src/agent_loop.py`, `src/tool_loop_guard.py`, `src/tool_parsing.py`, `tests/test_qwen_xml_tool_calls.py`, `tests/test_repeated_read_guard.py`.
- Resolution: Kept typed Qwen XML arguments and malformed/nested/duplicate rejection, combined with upstream declared environment-tool names. Repeated identical read failures remain bounded.
- Evidence: test_qwen_xml_tool_calls.py; test_tool_parsing_mixed_formats.py; test_repeated_read_guard.py.

### `ee5fdf1f` — Recover malformed local tool calls without guessing tool names

- Files: `src/agent_loop.py`, `src/tool_parsing.py`, `tests/test_qwen_xml_tool_calls.py`, `tests/test_repeated_read_guard.py`.
- Resolution: Malformed local calls get bounded correction without guessed tool names. The upstream Qwen text fallback now uses the same strict XML parser so it cannot reaccept rejected input.
- Evidence: test_qwen_xml_tool_calls.py; test_repeated_read_guard.py.

### `e8b912a5` — Recover study document searches and correlate reply review flags

- Files: `core/session_manager.py`, `routes/chat_helpers.py`, `routes/chat_routes.py`, `routes/diagnostics_routes.py`, `routes/history/history_routes.py`, `specs/documents-rag-uploads.md`, `specs/study-chat-failures-handoff.md`, `specs/study-chat-failures-validation.md`, `specs/tool-discovery.md`, `src/agent_loop.py`, `src/agent_tools/__init__.py`, `src/chat_processor.py`, `src/llm_core.py`, `src/pending_action.py`, `src/planning_validation.py`, `src/rag_singleton.py`, `src/rag_vector.py`, `src/settings.py`, `src/tool_approval_scopes.py`, `src/tool_capabilities.py`, `src/tool_execution.py`, `src/tool_index.py`, `src/tool_policy.py`, `src/tool_schemas.py`, `src/tool_security.py`, `src/tools/discovery.py`, `src/tools/knowledge.py`, `src/turn_log.py`, `static/js/chat.js`, `static/js/chatRenderer.js`, `tests/helpers/embedding_lanes.py`, `tests/test_agent_rounds_exhausted.py`, `tests/test_chat_preparation_spinner_js.py`, `tests/test_diagnostics_service_route.py`, `tests/test_external_context_tool_gate.py`, `tests/test_foreground_model_routing.py`, `tests/test_knowledge_tool.py`, `tests/test_llm_core_streaming.py`, `tests/test_local_tool_stall.py`, `tests/test_rag_shared_documents.py`, `tests/test_review_flag_js.py`, `tests/test_study_chat_recovery.py`, `tests/test_study_chat_retrieval.py`, `tests/test_study_planning_constraints.py`, `tests/test_tool_discovery.py`, `tests/test_turn_review_identity.py`.
- Resolution: Kept pending study intent, multilingual promise recovery, lazy shared RAG lookup, owner-scoped search, retrieval diagnostics and reply/message/turn correlation. Added indexed-knowledge capability to upstream authority while retaining explicit denials and workspace/media routing.
- Evidence: test_study*.py; test_knowledge_tool.py; test_turn_review_identity.py; test_review_flag_js.py; test_dev_integration_contracts.py.

### `eae3276b` — Bound single-source read failures and preserve fresh tool evidence

- Files: `src/agent_loop.py`, `src/context_compactor.py`, `src/tool_loop_guard.py`, `tests/test_context_tool_loop_trimming.py`, `tests/test_repeated_read_guard.py`, `tests/test_runtime_retry_progress.py`.
- Resolution: Kept canonical failed-read tracking, single-source stopping, alternative-source recovery and complete fresh assistant/tool exchanges. Upstream generic failed-round termination yields to the read guard for read-only batches.
- Evidence: test_repeated_read_guard.py; test_context_tool_loop_trimming.py; test_runtime_retry_progress.py.

### `fcf42f8c` — Clarify search evidence and guide capability discovery

- Files: `src/agent_tools/filesystem_tools.py`, `src/tool_loop_guard.py`, `src/tools/discovery.py`, `tests/test_code_nav_tools.py`, `tests/test_runtime_retry_progress.py`, `tests/test_tool_discovery.py`.
- Resolution: Retained explicit no-file/no-pattern-result text, discovery candidate caveats and bounded retry notices. Discovery schemas are registered in the new upstream tool_types registry and request authority permits discovery without authorizing discovered actions.
- Evidence: test_code_nav_tools.py; test_runtime_retry_progress.py; test_tool_discovery.py; test_dev_integration_contracts.py.

### `6d791e39` — Fix local model autostart and Cookbook lifecycle; update training preparation

- Files: `local_finetune/RUNBOOK.md`, `local_finetune/setup_remote.sh`, `local_finetune/train_lora.py`, `routes/cookbook_helpers.py`, `routes/cookbook_routes.py`, `routes/model_routes.py`, `src/local_model_startup.py`, `static/js/chat.js`, `static/js/cookbook.js`, `static/js/cookbookRunning.js`, `static/js/cookbookServe.js`, `static/js/localModelStartup.js`, `static/js/modelPicker.js`, `tests/test_cookbook_helpers.py`, `tests/test_cookbook_inventory_regressions.py`, `tests/test_local_model_startup.py`, `tests/test_model_routes.py`.
- Resolution: Retained the startup coordinator, authenticated saved-command startup, readiness/coalescing/cancellation handling, offline selection, cache filtering and task-format support. Combined upstream timeout/card disposal with endpoint preservation; live probes override stale persisted states. Training files remain exact. Native v2 GGUF filenames retain native schemas and caller-selected sampling instead of implicitly opting into upstream router settings.
- Evidence: test_local_model_startup.py; test_cookbook*.py; test_model_routes.py; test_dev_integration_contracts.py; test_odysseus_model_modes.py.

## Protected assets and deployment boundary

The production checkout remains at the original hash and clean. Its service, configuration, virtual environment, launch profiles, corpus/index and model weights were not changed. Ignored paths were inventoried without opening sealed evaluation content. Tests used temporary worker data, in-memory databases, `CHROMADB_PORT=1` and `HF_HUB_OFFLINE=1`; no production credentials were copied. No corpus migration/reindex, training, export, paid compute or push occurred.

All tracked `local_finetune` files match the original branch. Protected SHA256 values:

```
615584c9003344eefbbc28a28be247107b892f6438fb35fb10bc0f3eb69c80da  local_finetune/train_lora.py
511ec45ff14819e2afc7fee070bd1805396e1ce3de76ccbe98da4fa7d6cebbbf  local_finetune/setup_remote.sh
76a0a34bd507260fd6e36c422eecb16b41f7792e2d49b09650d668728a8f7f9a  local_finetune/RUNBOOK.md
```

## Validation

The isolated runtime uses Python 3.12.14, Node 22.23.3, and bubblewrap 0.13.0. Upstream Python requirements and npm dependencies were installed only in the integration environment. Exact installed Python versions are saved as `validation-requirements.txt` in the evidence directory. Native setup and dependency guidance in `website/setup.md` was reviewed; its installation/setup commands were not run against production.

| Check | Result | Evidence file |
| --- | --- | --- |
| Original branch startup/Cookbook/model/chat baseline | 404 passed, 1 skipped | `baseline-focused.log` |
| Initial integrated full suite | 14,508 passed, 60 failed, 59 skipped | `full-suite.log` |
| Second integrated full suite | 14,577 passed, 3 failed, 59 skipped; all three failures resolved and rechecked below | `full-final.log` |
| Final recheck of every initially failing module plus integration/discovery/product-route contracts | 1,868 passed | `recheck-final.log`, exact targets in `recheck-modules.txt` |
| Final closure of preview, module-identity, real-browser offline and tool-policy modules | 605 passed | `closure.log` |
| Native containment, workspace and artifact behavior with canonical interpreter | 70 passed | `canonical-runtime.log` |
| Web final synthesis, study recovery and exhausted-round behavior after the final correction | 124 passed | `synthesis-final.log` |
| Native v2 schemas/sampling and model-profile regression checks | 25 passed | `v2-native-final.log` |
| Frontend architecture | 43 maintained modules checked; 10 Node tests passed | `frontend-check.log`; final command repeated successfully |
| Syntax | 1,849 tracked non-training Python files parsed; 457 JavaScript files checked, service worker rechecked after final edit | `js-syntax.log`; final Python AST scan |
| Merge and whitespace integrity | No unmerged index entries; diff check against dev clean | Final Git checks |

The 60 failures in the first broad run were triaged as integration contract/routing/parser/sampling issues, deliberate branch behavior requiring updated upstream fixture expectations, missing generated configuration/offline-cache entries, or the copied interpreter environment. None were dismissed solely because the files merged automatically. The targeted final recheck executes the whole affected modules, including authorization-denial tests; it does not select only the formerly failing test cases.

Two workspace Python failures were reproduced on untouched pinned dev (`upstream-workspace.log`: 2 failed, 29 passed). The separate canonical environment fixed them and the broader containment checks without changing containment code. Broad tests used user systemd units capped at 6 GiB soft / 8 GiB hard memory limits.

The second broad run began before the last web-synthesis correction and therefore still reported that known failure. Its other two failures were a missing `find_tools` sample in the exhaustive preview-tool policy test and duplicate panels-loader cache identities. The sample was added without relaxing the exhaustive assertion; the duplicate cache URL was removed and offline browser fixtures now navigate to the deployed versioned URL. All 605 tests in these five modules passed on the final source, including the web-synthesis regression. The full suite was not repeated after these last corrections; its three recorded failures are resolved by this module-wide closure, rather than reported as a wholly green full run.

```bash
CHROMADB_PORT=1 HF_HUB_OFFLINE=1 /home/matas/odysseus-integration-backups/20261023/venv-canonical/bin/python -m pytest -q --tb=short tests/test_clean_agent_preview.py tests/test_frontend_module_version_parity.py tests/test_frontend_foundation_offline_js.py tests/test_notes_reference_browser.py tests/test_tool_policy.py
```

Reproduction from the integration worktree, with the prepared isolated environment:

```bash
B=/home/matas/odysseus-integration-backups/20261023
CHROMADB_PORT=1 HF_HUB_OFFLINE=1 "$B/venv-canonical/bin/python" -m pytest -q --tb=short
CHROMADB_PORT=1 HF_HUB_OFFLINE=1 "$B/venv-canonical/bin/python" -m pytest -q --tb=short $(cat "$B/recheck-modules.txt")
node scripts/check_frontend.mjs
node --test tests/frontendArchitecture.test.mjs
git diff --check 01566b158e627748f70ac402571f2f78241fb6f9
```

The initial baseline used the handoff's focused command: `python -m pytest tests/test_local_model_startup.py tests/test_cookbook*.py tests/test_model_routes.py tests/test_chat_preparation_spinner_js.py tests/test_chat_stream_errors_js.py tests/test_chat_model_provenance_js.py -q` from the detached original-branch worktree.

Ruff's F821 scan covers all 47 branch/integration Python source files and leaves the two upstream defects listed below (`ruff-current.log`). A diff check against the original branch reports pre-existing whitespace in four unchanged dev blobs: the docx and Mammoth distribution notices, `src/generated_images.py`, and `tests/test_settings_save_response_ok_js.py`. Their hashes match dev; third-party notices were preserved verbatim (`diff-check-original.log`).


## Remaining limits and cutover prerequisites

- No live-model, browser-to-production cold-start, multi-client, or real corpus validation was performed. Local mocked/contained tests establish software behavior, not end-to-end model quality.
- Historical five-call discovery loops and Lithuanian identifier/tag confusion remain model limitations; this merge does not claim to solve them.
- Upstream's native containment exposes canonical interpreter roots. The copied uv virtual environment initially linked through a noncanonical interpreter alias, which failed inside bubblewrap. The same two workspace tests failed at untouched upstream. A separate isolated environment normalizes that symlink; production remains unchanged. A future cutover must use a fresh compatible environment or normalize the interpreter symlink and repeat native Python checks before service restart.
- Dependency changes are installed only in isolated environments. The deployed environment and its data migration behavior still require an approved cutover procedure, a deliberate state backup, and readiness checks.
- Read-only Ruff audit identified upstream-existing undefined `repo` in Cookbook scan error logging and `history_session` in system-prompt skill handling. These were verified against the pinned target and are not represented as merge regressions or silently fixed here.
- Production cutover, restart and pushing remain separate actions requiring the user's authorization under the handoff.
