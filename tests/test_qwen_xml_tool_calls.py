import json
import time

import pytest

import src.agent_tools
from src.tool_parsing import parse_tool_blocks, strip_tool_blocks


def wrapped(name='read_file', parameters='<parameter=path>/srv/team/report</parameter>', close=True):
    return '<tool_call><function=' + name + '>' + parameters + '</function>' + ('</tool_call>' if close else '')


@pytest.mark.parametrize('close', [False, True])
def test_qwen_xml_reads_lithuanian_paths_and_strips_markup(close):
    text = 'Skaitau.\n' + wrapped(parameters='<parameter=path>/srv/užrašai/aprašas.txt</parameter>', close=close)
    blocks = parse_tool_blocks(text, skip_fenced=True)
    assert [(block.tool_type, block.content) for block in blocks] == [('read_file', '/srv/užrašai/aprašas.txt')]
    assert strip_tool_blocks(text, skip_fenced=True) == 'Skaitau.'


def test_qwen_xml_preserves_typed_line_ranges():
    blocks = parse_tool_blocks(wrapped(parameters=(
        '<parameter=path>/srv/team/report</parameter><parameter=offset>7</parameter><parameter=limit>12</parameter>'
    )))
    assert json.loads(blocks[0].content) == {'path': '/srv/team/report', 'offset': 7, 'limit': 12}


def test_qwen_xml_keeps_false_boolean_false():
    text = wrapped('grep', '<parameter=pattern>42</parameter><parameter=ignore_case>false</parameter>')
    block = parse_tool_blocks(text)[0]
    assert json.loads(block.content)['ignore_case'] is False
    assert json.loads(block.content)['pattern'] == '42'


@pytest.mark.parametrize('text', [
    wrapped('file'),
    wrapped(parameters='<parameter=path>/srv/team/report'),
    wrapped(parameters='<parameter=path>/a</parameter><parameter=path>/b</parameter>'),
    wrapped(parameters='<parameter=path>/a</parameter><parameter=offset>true</parameter>'),
    wrapped(parameters='<parameter=path>/a</parameter><parameter=offset>[]</parameter>'),
    wrapped(parameters='<function=bash><parameter=command>echo unsafe</parameter></function>'),
    '<tool_call><function=read_file><parameter=path>/a</parameter></tool_call>',
])
def test_malformed_or_unknown_qwen_calls_fail_closed(text):
    assert parse_tool_blocks(text) == []


def test_qwen_parameter_values_are_not_rescanned_as_other_calls():
    text = wrapped('write_file', (
        '<parameter=path>/srv/team/note</parameter>'
        '<parameter=content><bash>echo unsafe</bash></parameter>'
    ))
    blocks = parse_tool_blocks(text)
    assert [block.tool_type for block in blocks] == ['write_file']
    assert 'echo unsafe' in blocks[0].content


def test_ambiguous_nested_parameter_markup_is_not_rescanned():
    text = wrapped('write_file', (
        '<parameter=path>/srv/team/note</parameter>'
        '<parameter=content><invoke name="bash"><parameter name="command">echo unsafe</parameter></invoke></parameter>'
    ))
    assert parse_tool_blocks(text) == []


def test_unclosed_function_opener_flood_does_not_backtrack():
    started = time.monotonic()
    assert parse_tool_blocks('<tool_call>' + '<function=read_file>' * 20000) == []
    assert time.monotonic() - started < 1
