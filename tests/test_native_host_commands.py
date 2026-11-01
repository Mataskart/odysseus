from dataclasses import replace
import os
import shlex

import pytest

from src import containment, tool_execution
from src.agent_runtime.authority import RequestAuthority, OperationGrant, ExactOperation
from src.agent_runtime.process_resources import (
    bind_process_operation, host_command_access_allowed, resolve_process_operation,
    intersect_launch_scopes, validate_launch_spec,
)
from src.agent_runtime.resources import NativeBackendResource, ProcessLaunchScope, ResourceIdentityError
from src.agent_tools.subprocess_tools import _owned_spec, BashTool
from tests.process_resource_helpers import launch_authority


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv('ODYSSEUS_HOST_COMMAND_OWNERS', 'alice')
    monkeypatch.setattr(tool_execution, '_owner_is_admin', lambda owner: owner == 'alice')


def test_host_access_needs_both_server_opt_in_and_admin(enabled, monkeypatch):
    assert host_command_access_allowed('alice')
    assert not host_command_access_allowed('bob')
    assert not host_command_access_allowed('')
    monkeypatch.setattr(tool_execution, '_owner_is_admin', lambda owner: False)
    assert not host_command_access_allowed('alice')
    monkeypatch.delenv('ODYSSEUS_HOST_COMMAND_OWNERS')
    assert not host_command_access_allowed('alice')


def test_request_environment_cannot_enable_host_access(tmp_path, monkeypatch):
    monkeypatch.delenv('ODYSSEUS_HOST_COMMAND_OWNERS', raising=False)
    spec = _owned_spec(str(tmp_path), {'ODYSSEUS_HOST_COMMAND_OWNERS': 'alice'}, 10, owner='alice')
    assert not spec.host_access
    assert containment.FILESYSTEM in spec.required
    assert not containment.agent_spec(str(tmp_path), {}, 10, host_access=True).host_access


def test_host_scope_is_sealed_serialized_and_revocable(enabled, tmp_path, monkeypatch):
    authority = RequestAuthority('request', 'alice', 'thread', str(tmp_path), (OperationGrant('bash'),))
    bound = resolve_process_operation(authority, ExactOperation.normalize('bash', 'pwd'), NativeBackendResource('bash'))
    scope = bound.launch.scope
    assert scope.host_access
    assert containment.FILESYSTEM not in scope.required
    assert ProcessLaunchScope.from_dict(scope.to_dict()) == scope
    spec = _owned_spec(str(tmp_path), {}, 10, owner='alice')
    validate_launch_spec(bound.launch, spec)
    with pytest.raises(ResourceIdentityError):
        validate_launch_spec(bound.launch, replace(spec, host_access=False))
    monkeypatch.delenv('ODYSSEUS_HOST_COMMAND_OWNERS')
    with pytest.raises(ResourceIdentityError, match='not enabled'):
        with bind_process_operation(bound):
            pytest.fail('revoked host launch ran')


def test_restricted_parent_cannot_gain_host_access(enabled, tmp_path):
    authority = RequestAuthority('request', 'alice', 'thread', str(tmp_path), (OperationGrant('bash'),))
    host = authority.launch_scopes[0]
    restricted = replace(host, host_access=False, required=containment.DEFAULT_REQUIRED)
    assert intersect_launch_scopes((restricted,), (host,)) == ()
    assert intersect_launch_scopes((host,), (restricted,)) == (restricted,)
    legacy = restricted.to_dict()
    legacy.pop('host_access')
    assert not ProcessLaunchScope.from_dict(legacy).host_access


def test_host_boundary_reports_no_filesystem_confinement(enabled, tmp_path, monkeypatch):
    monkeypatch.setattr(containment.shutil, 'which', lambda _: '/usr/bin/bwrap')
    spec = _owned_spec(str(tmp_path), {}, 10, owner='alice')
    assert containment.FILESYSTEM not in spec.requested
    assert containment.FILESYSTEM not in containment._bwrap_provides(spec)
    selected, enforced = containment._select(spec)
    assert selected.name == 'process_group'
    assert containment.WALL_CLOCK in enforced
    assert containment.PROCESS_TREE not in enforced
    assert containment.FILESYSTEM not in enforced


@pytest.mark.asyncio
async def test_host_command_reads_real_system_and_keeps_user_identity(enabled, tmp_path, monkeypatch):
    from src import constants
    from src.agent_runtime import process_resources
    workspace = tmp_path / 'home'
    workspace.mkdir()
    control = workspace / 'app.db'
    control.touch()
    monkeypatch.setattr(constants, 'APP_DB', str(control))
    monkeypatch.setattr(containment, '_store_path', lambda: tmp_path / 'grants.json')
    monkeypatch.setattr(process_resources, '_LAUNCH_DIR', tmp_path / 'launches')
    outside = tmp_path / 'outside.txt'
    outside.write_text('outside-workspace-ok')
    command = f'id -u; ls -ld /dev; cat /proc/filesystems; cat {shlex.quote(str(outside))}; printf device-ok >/dev/null'
    with launch_authority(command, workspace, owner='alice'):
        result = await BashTool().execute(command, {'owner': 'alice', 'session_id': 'chat'})
    assert result['exit_code'] == 0, result
    assert str(os.getuid()) == result['output'].splitlines()[0]
    assert '/dev' in result['output'] and 'proc' in result['output']
    assert 'outside-workspace-ok' in result['output']
    assert result['containment']['host_access'] is True
    assert result['containment']['mechanism'] == 'process_group'
    assert 'filesystem' not in result['containment']['enforced']
    assert result['teardown']['dead'] is True


@pytest.mark.asyncio
async def test_host_python_reads_outside_workspace(enabled, tmp_path, monkeypatch):
    from src.agent_tools.subprocess_tools import PythonTool
    from src.agent_runtime import process_resources
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('python-host-ok')
    monkeypatch.setattr(containment, '_store_path', lambda: tmp_path / 'grants.json')
    monkeypatch.setattr(process_resources, '_LAUNCH_DIR', tmp_path / 'launches')
    command = f'from pathlib import Path; print(Path({str(outside)!r}).read_text())'
    with launch_authority(command, workspace, owner='alice', tool='python'):
        result = await PythonTool().execute(command, {'owner': 'alice', 'session_id': 'chat'})
    assert result['exit_code'] == 0, result
    assert 'python-host-ok' in result['output']
    assert result['teardown']['dead'] is True
