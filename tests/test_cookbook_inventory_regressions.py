import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from routes.cookbook_helpers import _cached_model_scan_script
from routes.model_routes import _picker_models_for_endpoint


ROOT = Path(__file__).resolve().parents[1]


def test_hf_scan_excludes_metadata_and_static_embeddings_without_deleting(tmp_path):
    cache = tmp_path / 'hub'
    def snapshot(repo, config, weights=None):
        folder = cache / f'models--org--{repo}' / 'snapshots' / 'revision'
        folder.mkdir(parents=True)
        (folder / 'config.json').write_text(json.dumps(config))
        if weights:
            (folder / weights).write_bytes(b'weights')
        return folder

    metadata = snapshot('metadata', {})
    embedding = snapshot('embedding', {'model_type': 'model2vec', 'architectures': ['StaticModel']}, 'model.safetensors')
    snapshot('chat', {'architectures': ['ExampleForCausalLM']}, 'model.safetensors')
    snapshot('gguf', {}, 'model.gguf')
    snapshot('adapter', {}, 'adapter_model.safetensors')
    incomplete = cache / 'models--org--partial' / 'blobs'
    incomplete.mkdir(parents=True)
    (incomplete / 'download.incomplete').write_bytes(b'partial')
    script = _cached_model_scan_script().split('for _hf_cache in hf_cache_paths():')[0]
    script += f'\nscan_hf({str(cache)!r})\nprint(json.dumps(models))\n'
    result = subprocess.run([sys.executable, '-c', script], check=True, text=True, capture_output=True)
    models = {m['repo_id']: m for m in json.loads(result.stdout)}
    assert set(models) == {'org/chat', 'org/gguf', 'org/adapter', 'org/partial'}
    assert models['org/partial']['has_incomplete']
    assert models['org/adapter']['is_adapter']
    assert metadata.exists() and (embedding / 'model.safetensors').exists()


def test_local_picker_collapses_hf_repository_alias_but_preserves_other_models():
    gguf = '/cache/models--local--Example/snapshots/revision/example.gguf'
    other_quant = '/cache/models--local--Example/snapshots/revision/example-q8.gguf'
    endpoint = SimpleNamespace(cached_models=json.dumps([gguf, other_quant]),
                               pinned_models=json.dumps(['local/Example', 'other/model']), hidden_models=None)
    models, pinned = _picker_models_for_endpoint(endpoint, 'http://localhost:8000/v1', 'local')
    assert models == [gguf, other_quant, 'other/model']
    assert pinned == ['other/model']
    endpoint.cached_models = '[]'
    assert _picker_models_for_endpoint(endpoint, 'http://localhost:8000/v1', 'local')[0] == ['local/Example', 'other/model']
    assert _picker_models_for_endpoint(endpoint, 'https://api.example.com/v1', 'api')[0] == ['local/Example', 'other/model']


def test_task_clearability_respects_stopped_status_over_old_ready_output():
    source = (ROOT / 'static/js/cookbookRunning.js').read_text()
    def function(name, next_name):
        return source.split(f'function {name}(', 1)[1].split(f'\nfunction {next_name}(', 1)[0]
    ready = 'function _serveOutputLooksReady(' + function('_serveOutputLooksReady', '_normalizeTaskForDisplay')
    clear = 'function _canClearTask(' + function('_canClearTask', '_clearPillLabel')
    script = ready + clear + '''
      function _downloadOutputLooksActive() { return false; }
      const task = { type: 'serve', _serveReady: true, output: 'Application startup complete' };
      console.log(JSON.stringify(['running', 'ready', 'stopped', 'error'].map(status => _canClearTask({...task, status}))));
    '''
    result = subprocess.run(['node', '-e', script], check=True, text=True, capture_output=True)
    assert json.loads(result.stdout) == [False, False, True, True]


def test_terminal_poll_can_reattach_same_card_after_hiding():
    source = (ROOT / 'static/js/cookbookRunning.js').read_text()
    reconnect = 'async function _reconnectTask(' + source.split('async function _reconnectTask(', 1)[1].split('// ── Background monitor', 1)[0]
    script = reconnect + '''
      let visible = true, calls = 0;
      const output = {textContent: ''};
      const wrap = {classList: {contains: () => false}};
      const el = {isConnected: true, querySelector: selector => selector === '.cookbook-output-wrap' ? wrap : output};
      function _isRunningTabVisible() { return visible; }
      function _tmuxCmd() { return 'capture'; }
      const TASK_POLL_INTERVAL_MS = 1;
      async function fetch() { calls++; visible = false; return {json: async () => ({exit_code: 0, stdout: ''})}; }
      await _reconnectTask(el, {sessionId: 'serve-test'});
      visible = true;
      await _reconnectTask(el, {sessionId: 'serve-test'});
      console.log(JSON.stringify({calls, aborted: !el._abort || el._abort.signal.aborted}));
    '''
    result = subprocess.run(['node', '--input-type=module', '-e', script], check=True, text=True, capture_output=True)
    assert json.loads(result.stdout) == {'calls': 2, 'aborted': True}


def test_llama_listening_marker_matches_backend_and_frontend():
    from routes.cookbook_helpers import _parse_serve_phase
    source = (ROOT / 'static/js/cookbookRunning.js').read_text()
    parser = 'function _parseServePhase(' + source.split('function _parseServePhase(', 1)[1].split('// ── Port auto-increment', 1)[0]
    snapshots = [
        '0.04.283.010 I srv llama_server: listening on http://0.0.0.0:8000',
        'main: listening on http://127.0.0.1:8000',
        'srv llama_server: listening on\n http://0.0.0.0:8000',
        'srv llama_server: model loaded',
    ]
    expected = ['ready', 'ready', 'ready', None]
    assert [_parse_serve_phase(s).get('status') for s in snapshots] == expected
    script = parser + 'console.log(JSON.stringify(' + json.dumps(snapshots) + '.map(s => _parseServePhase(s).status || null)));'
    result = subprocess.run(['node', '-e', script], check=True, text=True, capture_output=True)
    assert json.loads(result.stdout) == expected


def test_local_serve_rechecks_stale_stopped_state_and_respects_exit(monkeypatch, tmp_path):
    import inspect
    import routes.cookbook_routes as routes
    state = tmp_path / 'cookbook.json'
    state.write_text(json.dumps({'tasks': [
        {'sessionId': 'serve-live', 'type': 'serve', 'status': 'stopped'},
        {'sessionId': 'serve-clean', 'type': 'serve', 'status': 'stopped'},
        {'sessionId': 'serve-failed', 'type': 'serve', 'status': 'running'},
        {'sessionId': 'serve-gone', 'type': 'serve', 'status': 'running',
         'output': 'srv llama_server: listening on http://0.0.0.0:8000'},
    ]}))
    monkeypatch.setattr(routes, 'COOKBOOK_STATE_FILE', state)
    monkeypatch.setattr(routes, 'IS_WINDOWS', False)
    def run(cmd, **kwargs):
        sid = cmd[cmd.index('-t') + 1]
        output = 'srv llama_server: listening on http://0.0.0.0:8000'
        if sid == 'serve-clean': output += '\n=== Process exited with code 0 ==='
        if sid == 'serve-failed': output += '\n=== Process exited with code 1 ==='
        return SimpleNamespace(returncode=int(sid == 'serve-gone'), stdout=output)
    monkeypatch.setattr(subprocess, 'run', run)
    router = routes.setup_cookbook_routes()
    endpoint = next(r.endpoint for r in router.routes if r.path == '/api/cookbook/tasks/status')
    compute = inspect.getclosurevars(endpoint).nonlocals['_cookbook_tasks_status_sync']
    cells = dict(zip(compute.__code__.co_freevars, compute.__closure__))
    cells['_maybe_sweep_orphans'].cell_contents = lambda *args: None
    tasks = compute()['tasks']
    assert [t['status'] for t in tasks] == ['ready', 'stopped', 'error', 'stopped']
    assert [t['phase'] for t in tasks] == ['ready', '', '', '']


def test_picker_live_probe_overrides_stale_inventory_availability():
    source = (ROOT / 'static/js/modelPicker.js').read_text()
    function = 'function _getAllModels(' + source.split('function _getAllModels(', 1)[1].split('\n  function ', 1)[0]
    script = '''
      let _localProbe = {};
      let item = {endpoint_id:'local', category:'local', models:['model'], offline:true};
      const window = {modelsModule: {getCachedItems: () => [item]}};
      const sortModelObjects = values => values;
    ''' + function + '''
      if (!_getAllModels()[0].stale) throw new Error('Lost cached offline fallback');
      _localProbe = {local: {alive:true}};
      if (_getAllModels()[0].stale || _getAllModels()[0].offline) throw new Error('Live probe must override stale inventory');
      item.offline = false;
      _localProbe.local.alive = false;
      if (!_getAllModels()[0].stale || !_getAllModels()[0].offline) throw new Error('Failed live probe must override cached online');
    '''
    subprocess.run(['node', '-e', script], check=True, text=True, capture_output=True)
