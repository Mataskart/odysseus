import asyncio
import json
from types import SimpleNamespace

import pytest

from src.tools.discovery import discover_tools
from src.agent_tools import FUNCTION_TOOL_SCHEMAS


def set_index(monkeypatch, names):
    monkeypatch.setattr('src.tool_index.get_tool_index', lambda: SimpleNamespace(retrieve=lambda query, k: names))


def test_discovery_filters_disabled_and_stale_results(monkeypatch):
    set_index(monkeypatch, ['bash', 'removed_tool', 'read_file', 'grep'])
    _, result = asyncio.run(discover_tools('{"query":"inspect source", "limit":2}', FUNCTION_TOOL_SCHEMAS, {'bash'}))
    assert result['discovered_tools'] == ['read_file', 'grep']
    assert 'bash' not in [tool['name'] for tool in json.loads(result['output'])['tools']]


def test_discovery_falls_back_when_index_fails(monkeypatch):
    def unavailable():
        raise RuntimeError('index offline')
    monkeypatch.setattr('src.tool_index.get_tool_index', unavailable)
    _, result = asyncio.run(discover_tools('{"query":"read_file", "limit":1}', FUNCTION_TOOL_SCHEMAS, set()))
    assert result['discovered_tools'] == ['read_file']
    assert json.loads(result['output'])['method'] == 'lexical_fallback'


@pytest.mark.parametrize('content', ['{}', '[]', '{"query":""}', '{"query":"files","limit":99}', '{"query":"files","limit":true}'])
def test_discovery_validates_arguments(content):
    _, result = asyncio.run(discover_tools(content, [], set()))
    assert result['exit_code'] == 1


def test_discovery_recovers_missing_file_tools_in_real_loop(monkeypatch):
    import src.agent_loop as al
    set_index(monkeypatch, ['bash', 'read_file'])
    monkeypatch.setattr(al, 'get_setting', lambda key, default=None: default)
    monkeypatch.setattr(al, 'get_mcp_manager', lambda: None)
    monkeypatch.setattr(al, 'blocked_tools_for_owner', lambda owner: set())
    monkeypatch.setattr(al, 'estimate_tokens', lambda *a, **k: 100)
    monkeypatch.setattr(al, '_build_system_prompt', lambda messages, *a, **k: (messages, []))
    offered_rounds = []
    executed = []

    async def execute(block, **kwargs):
        executed.append(block.tool_type)
        return block.tool_type, {'output': 'OpenJev configuration', 'exit_code': 0}

    async def stream(candidates, messages, **kwargs):
        offered = {schema['function']['name'] for schema in kwargs['tools']}
        offered_rounds.append(offered)
        if len(offered_rounds) == 1:
            assert 'find_tools' in offered
            assert 'read_file' not in offered
            call = {'name': 'find_tools', 'arguments': json.dumps({'query': 'inspect OpenJev source files'})}
        elif len(offered_rounds) == 2:
            assert 'read_file' in offered
            assert 'bash' not in offered
            call = {'name': 'read_file', 'arguments': json.dumps({'path': 'specs/openjev.md'})}
        else:
            yield 'data: ' + json.dumps({'delta': 'Suggestions based on the configuration.'}) + '\n\n'
            yield 'data: [DONE]\n\n'
            return
        yield 'data: ' + json.dumps({'type': 'tool_calls', 'calls': [call]}) + '\n\n'
        yield 'data: [DONE]\n\n'

    monkeypatch.setattr(al, 'execute_tool_block', execute)
    monkeypatch.setattr(al, 'stream_llm_with_fallback', stream)

    async def run():
        return [chunk async for chunk in al.stream_agent_loop(
            'http://127.0.0.1:8000/v1', 'Qwen3.8-35B',
            [{'role': 'user', 'content': "OK so look at what it's currently set up to do and suggest improvements for the RAG pipeline"}],
            relevant_tools={'suggest_document'}, disabled_tools={'bash'},
            max_rounds=4, log_turns=False, _is_teacher_run=True,
        )]
    events = asyncio.run(run())
    assert len(offered_rounds) == 3
    assert executed == ['read_file']
    assert any('Suggestions based' in event for event in events)
