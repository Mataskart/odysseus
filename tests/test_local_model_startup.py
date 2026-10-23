import asyncio
import json
from types import SimpleNamespace

import pytest

from src.local_model_startup import LocalModelStartup, saved_launch_profile


def endpoint(**kwargs):
    values = dict(id='local-test', base_url='http://localhost:8000/v1', api_key=None,
                  cached_models='["/cache/models--org--model/snapshots/abc/model.gguf"]',
                  pinned_models='["org/model"]')
    values.update(kwargs)
    return SimpleNamespace(**values)


def state():
    return {'presets': [{'model': 'org/model', 'cmd': 'llama-server -m /model.gguf --port 8000',
                         'remoteHost': '', 'fields': {}}]}


def test_saved_preset_must_match_model_port_and_host():
    assert saved_launch_profile(endpoint(), state(), {})['repo_id'] == 'org/model'
    assert saved_launch_profile(endpoint(base_url='http://localhost:8001/v1'), state(), {}) is None
    assert saved_launch_profile(endpoint(base_url='http://remote:8000/v1'), state(), {}) is None
    assert saved_launch_profile(endpoint(cached_models='[]', pinned_models='["other/model"]'), state(), {}) is None
    ambiguous = state()
    ambiguous['presets'].append({**ambiguous['presets'][0], 'cmd': 'llama-server -m /different.gguf --port 8000'})
    assert saved_launch_profile(endpoint(), ambiguous, {}) is None


@pytest.mark.asyncio
async def test_concurrent_messages_share_one_startup_and_wait_for_readiness(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps(state()))
    launches = []
    ready = False
    async def launch(profile):
        launches.append(profile)
        return {'ok': True}
    startup = LocalModelStartup(path, launch, poll_interval=0.001)
    async def probe(ep, fresh=False):
        await asyncio.sleep(0)
        return {'alive': ready, 'loading': False}
    startup.probe = probe
    results = await asyncio.gather(*(startup.ensure(endpoint()) for _ in range(5)))
    assert all(result['status'] == 'starting' for result in results)
    await asyncio.sleep(0.005)
    assert len(launches) == 1
    ready = True
    await startup.jobs['local-test']['task']
    assert await startup.ensure(endpoint()) == {'status': 'ready'}


@pytest.mark.asyncio
async def test_loading_model_is_not_launched_twice_and_failure_has_cooldown(tmp_path):
    path = tmp_path / 'state.json'
    path.write_text(json.dumps(state()))
    launches = []
    async def launch(profile):
        launches.append(profile)
        return {'ok': False}
    startup = LocalModelStartup(path, launch, timeout=0.01, poll_interval=0.001)
    async def loading(ep, fresh=False):
        return {'alive': False, 'loading': True}
    startup.probe = loading
    assert (await startup.ensure(endpoint()))['status'] == 'starting'
    await startup.jobs['local-test']['task']
    assert (await startup.ensure(endpoint()))['status'] == 'error'
    assert launches == []


@pytest.mark.asyncio
async def test_no_saved_launch_does_not_execute_anything(tmp_path):
    async def launch(profile):
        pytest.fail('must not launch an unknown profile')
    startup = LocalModelStartup(tmp_path / 'state.json', launch)
    async def offline(ep, fresh=False):
        return {'alive': False, 'loading': False}
    startup.probe = offline
    assert (await startup.ensure(endpoint()))['status'] == 'error'
    assert not startup.jobs


def test_manual_launch_remembered_without_token(tmp_path):
    from routes.cookbook_helpers import ServeRequest
    startup = LocalModelStartup(tmp_path / 'state.json', None)
    request = ServeRequest(repo_id='org/model', cmd='llama-server --port 8000', hf_token='secret')
    startup.remember(endpoint(), request)
    assert 'secret' not in startup.profiles_path.read_text()
    assert startup.profile(endpoint())['cmd'] == request.cmd


@pytest.mark.asyncio
async def test_probe_uses_real_tls_settings_and_handles_http_responses(tmp_path, monkeypatch):
    import httpx
    real_client = httpx.AsyncClient
    responses = [httpx.Response(503), httpx.Response(200, json={'data': [{'id': 'org/model'}]}),
                 httpx.Response(500, text='Internal Server Error')]
    def handler(request):
        assert str(request.url) == 'http://localhost:8000/v1/models'
        return responses.pop(0)
    def client(**kwargs):
        return real_client(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    startup = LocalModelStartup(tmp_path / 'state.json', None)
    assert await startup.probe(endpoint(), fresh=True) == {'alive': False, 'loading': True}
    assert await startup.probe(endpoint(), fresh=True) == {'alive': True, 'loading': False}
    assert await startup.probe(endpoint(), fresh=True) == {'alive': False, 'loading': False}


def test_browser_startup_reports_plain_text_500_and_stops_on_cancel():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    script = '''
      import {ensureLocalModel} from './static/js/localModelStartup.js';
      const route = {endpoint_id: 'local-test', model: 'org/model'};
      const controller = new AbortController();
      let calls = 0;
      globalThis.fetch = async () => {
        calls++;
        if (calls === 1) return new Response(JSON.stringify({items: [{endpoint_id:'local-test',category:'local'}]}));
        return new Response('Internal Server Error', {status:500});
      };
      let error = '';
      try { await ensureLocalModel(route, {signal:controller.signal, onProgress:()=>{}}); }
      catch (e) { error = e.message; }
      if (!error.includes('HTTP 500') || error.includes('JSON.parse')) throw new Error(error);
      calls = 0;
      globalThis.fetch = async () => {
        calls++;
        if (calls === 1) return new Response(JSON.stringify({items: [{endpoint_id:'local-test',category:'local'}]}));
        return new Response(JSON.stringify({status:'starting',elapsed:1}));
      };
      try { await ensureLocalModel(route, {signal:controller.signal, onProgress:()=>controller.abort()}); }
      catch (e) { if(e.name !== 'AbortError') throw e; }
      if(calls !== 2) throw new Error('Unexpected request after cancellation');
    '''
    subprocess.run(['node', '--input-type=module', '-e', script], cwd=root, check=True, capture_output=True, text=True)


def test_startup_routes_enforce_endpoint_owner_and_model_permissions(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    import core.database as database
    import routes.cookbook_routes as cookbook
    import src.local_model_startup as module

    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    database.ModelEndpoint.__table__.create(engine)
    with Session(engine) as db:
        for name, owner in [('shared', None), ('private', 'alice')]:
            db.add(database.ModelEndpoint(id=name, name=name, owner=owner,
                   base_url='http://localhost:8000/v1', endpoint_kind='local',
                   cached_models='["org/model"]', is_enabled=True))
        db.commit()
    monkeypatch.setattr(database, 'SessionLocal', lambda: Session(engine))
    monkeypatch.setattr(cookbook, 'COOKBOOK_STATE_FILE', str(tmp_path / 'state.json'))
    calls = []
    class Startup:
        async def status(self, ep):
            return {'alive': False, 'autostart': True}
        async def ensure(self, ep):
            calls.append(ep.id)
            return {'status': 'starting'}
    monkeypatch.setattr(module, 'LocalModelStartup', lambda *args: Startup())
    app = FastAPI()
    privileges = {}
    app.state.auth_manager = SimpleNamespace(is_configured=True, is_admin=lambda user: False,
                                             get_privileges=lambda user: privileges)
    @app.middleware('http')
    async def identify(request, call_next):
        request.state.current_user = 'bob'
        return await call_next(request)
    app.include_router(cookbook.setup_cookbook_routes())
    with TestClient(app) as client:
        assert set(client.get('/api/local-models/status').json()) == {'shared'}
        assert client.post('/api/local-models/private/ensure-running', json={'model':'org/model'}).status_code == 404
        assert client.post('/api/local-models/shared/ensure-running', json={'model':'unknown'}).status_code == 400
        privileges['block_all_models'] = True
        assert client.post('/api/local-models/shared/ensure-running', json={'model':'org/model'}).status_code == 403
        assert not calls
        privileges.clear()
        result = client.post('/api/local-models/shared/ensure-running', json={'model':'org/model', 'cmd':'evil'})
        assert result.status_code == 200 and result.json()['status'] == 'starting'
        assert calls == ['shared']
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('as_mapping', [False, True])
async def test_autostart_records_task_in_both_saved_state_formats(tmp_path, monkeypatch, as_mapping):
    import routes.cookbook_routes as cookbook
    import src.local_model_startup as module
    path = tmp_path / 'state.json'
    previous = {'sessionId': 'serve-old', 'status': 'stopped'}
    tasks = {'serve-old': previous} if as_mapping else [previous]
    path.write_text(json.dumps({'tasks': tasks, 'presets': [{'name': 'Keep me'}]}))
    monkeypatch.setattr(cookbook, 'COOKBOOK_STATE_FILE', str(path))
    launches = []
    def startup_factory(state_path, launch):
        launches.append(launch)
        return SimpleNamespace()
    monkeypatch.setattr(module, 'LocalModelStartup', startup_factory)
    cookbook.setup_cookbook_routes()
    launch = launches[0]
    async def serve(request, profile):
        return {'ok': True, 'session_id': 'serve-new', 'endpoint_id': 'local-test'}
    cells = dict(zip(launch.__code__.co_freevars, launch.__closure__))
    cells['_launch_model_serve'].cell_contents = serve
    result = await launch({'repo_id': 'org/model', 'cmd': 'llama-server --port 8000'})
    saved = json.loads(path.read_text())
    assert result['ok']
    assert saved['tasks'][0] == previous
    assert saved['tasks'][1]['sessionId'] == 'serve-new'
    assert saved['tasks'][1]['_endpointId'] == 'local-test'
    assert saved['presets'] == [{'name': 'Keep me'}]
