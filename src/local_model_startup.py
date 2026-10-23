"""Start previously configured local models, with one startup per endpoint."""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from core.atomic_io import atomic_write_json
from src.endpoint_resolver import build_models_url, build_headers

logger = logging.getLogger(__name__)


def is_local_launch_endpoint(base_url):
    url = urlparse(base_url)
    return url.scheme in {'http', 'https'} and url.hostname in {'localhost', '127.0.0.1', '::1'}


def model_repository(model):
    match = re.search(r'models--([^/\\]+)--([^/\\]+)[/\\]snapshots[/\\]', model)
    return f'{match.group(1)}/{match.group(2)}' if match else model


def saved_launch_profile(endpoint, state, profiles):
    if not is_local_launch_endpoint(endpoint.base_url):
        return None
    models = json.loads(endpoint.cached_models or '[]') + json.loads(endpoint.pinned_models or '[]')
    repositories = {model_repository(model) for model in models}
    profile = profiles.get(endpoint.id)
    if (profile and profile.get('base_url') == endpoint.base_url
            and profile.get('request', {}).get('repo_id') in repositories):
        return profile['request']
    port = urlparse(endpoint.base_url).port or 80
    matches = []
    for preset in state.get('presets', []):
        if preset.get('remoteHost') or preset.get('model') not in repositories:
            continue
        command = preset.get('cmd', '')
        command_port = re.search(r'--port(?:\s+|=)(\d+)\b', command)
        if not command_port or int(command_port.group(1)) != port:
            continue
        fields = preset.get('fields') or {}
        matches.append({'repo_id': preset['model'], 'cmd': command,
                        'env_prefix': fields.get('venv') or None,
                        'gpus': fields.get('gpus') or None})
    # Multiple different presets are ambiguous until one is actually launched.
    commands = {profile['cmd'] for profile in matches}
    return matches[-1] if len(commands) == 1 else None


class LocalModelStartup:
    def __init__(self, state_path, launch, timeout=600, poll_interval=1):
        self.state_path = Path(state_path)
        self.profiles_path = self.state_path.with_name('local_model_launches.json')
        self.launch = launch
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.jobs = {}
        self.health_cache = {}

    def profile(self, endpoint):
        def read(path):
            try:
                return json.loads(path.read_text())
            except (OSError, ValueError):
                return {}
        return saved_launch_profile(endpoint, read(self.state_path), read(self.profiles_path))

    def remember(self, endpoint, request):
        if request.remote_host or not is_local_launch_endpoint(endpoint.base_url):
            return
        try:
            profiles = json.loads(self.profiles_path.read_text())
        except (OSError, ValueError):
            profiles = {}
        profiles[endpoint.id] = {'base_url': endpoint.base_url,
                                 'request': request.model_dump(exclude={'hf_token'})}
        atomic_write_json(str(self.profiles_path), profiles, indent=2)
        self.health_cache.pop(endpoint.id, None)

    async def probe(self, endpoint, fresh=False):
        cached = self.health_cache.get(endpoint.id)
        if not fresh and cached and time.monotonic() - cached[0] < 3:
            return cached[1]
        from src.tls_overrides import llm_verify
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False, verify=llm_verify()) as client:
                response = await client.get(build_models_url(endpoint.base_url), headers=build_headers(endpoint.api_key, endpoint.base_url))
            body = response.json() if response.is_success else {}
            online = response.is_success and isinstance(body, dict) and bool(body.get('data') or body.get('models'))
            status = {'alive': online, 'loading': response.status_code == 503}
        except (httpx.HTTPError, ValueError):
            status = {'alive': False, 'loading': False}
        self.health_cache[endpoint.id] = (time.monotonic(), status)
        return status

    async def status(self, endpoint):
        health = await self.probe(endpoint)
        job = self.jobs.get(endpoint.id)
        return {**health, 'autostart': self.profile(endpoint) is not None,
                'starting': bool(job and not job['task'].done())}

    async def ensure(self, endpoint):
        job = self.jobs.get(endpoint.id)
        if job and not job['task'].done():
            return {'status': 'starting', 'elapsed': int(time.monotonic() - job['started'])}
        health = await self.probe(endpoint, fresh=True)
        if health['alive']:
            return {'status': 'ready'}
        if job and job.get('error') and time.monotonic() - job['finished'] < 30:
            return {'status': 'error', 'error': job['error']}
        profile = self.profile(endpoint)
        if not profile:
            return {'status': 'error', 'error': 'This model is offline and has no saved local launch. Launch it once in Cookbook.'}
        # No await between rechecking and publishing: concurrent sends share the job.
        job = self.jobs.get(endpoint.id)
        if not job or job['task'].done():
            job = {'started': time.monotonic(), 'error': None}
            job['task'] = asyncio.create_task(self._start(endpoint, profile, health['loading'], job))
            self.jobs[endpoint.id] = job
        return {'status': 'starting', 'elapsed': int(time.monotonic() - job['started'])}

    async def _start(self, endpoint, profile, already_loading, job):
        try:
            async with asyncio.timeout(self.timeout):
                if not already_loading:
                    result = await self.launch(profile)
                    if not result.get('ok'):
                        raise RuntimeError('The saved model launch failed. Check its Cookbook output.')
                    job['session_id'] = result.get('session_id')
                while True:
                    health = await self.probe(endpoint, fresh=True)
                    if health['alive']:
                        return
                    session_id = job.get('session_id')
                    if session_id:
                        from routes.shell_routes import TMUX_LOG_DIR
                        log = TMUX_LOG_DIR / f'{session_id}.log'
                        if log.exists():
                            with log.open('rb') as stream:
                                stream.seek(max(0, log.stat().st_size - 4096))
                                tail = stream.read().decode(errors='replace')
                            if re.search(r'=== Process exited with code\s+-?\d+', tail, re.I):
                                raise RuntimeError('The model stopped during startup. Check its Cookbook output.')
                    await asyncio.sleep(self.poll_interval)
        except TimeoutError:
            job['error'] = 'Model startup timed out. Check its Cookbook output before trying again.'
        except Exception:
            logger.exception('Local model startup failed for endpoint %s', endpoint.id)
            job['error'] = 'The model could not start. Check its Cookbook output.'
        finally:
            job['finished'] = time.monotonic()
