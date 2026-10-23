async function readResponse(response, action) {
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`${action} failed (HTTP ${response.status}). The server returned an invalid response; please try again.`);
  }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.error;
    throw new Error(detail || `${action} failed (HTTP ${response.status}).`);
  }
  return data;
}

export async function fetchLocalModelStatus(signal) {
  const response = await fetch('/api/local-models/status', { credentials: 'same-origin', signal });
  return readResponse(response, 'Model availability check');
}

function endpointBase(value) {
  return String(value || '').replace(/\/(chat\/completions|completions|models)\/?$/, '').replace(/\/$/, '');
}

export async function ensureLocalModel(route, { signal, onProgress }) {
  const response = await fetch('/api/models?background=false', { credentials: 'same-origin', signal });
  const inventory = await readResponse(response, 'Model selection check');
  const endpoint = (inventory.items || []).find(item => route.endpoint_id
    ? item.endpoint_id === route.endpoint_id
    : endpointBase(item.url) === endpointBase(route.endpoint_url));
  if (!endpoint || endpoint.category !== 'local') return;
  const started = Date.now();
  while (Date.now() - started < 610000) {
    signal.throwIfAborted();
    const result = await fetch(`/api/local-models/${encodeURIComponent(endpoint.endpoint_id)}/ensure-running`, {
      method: 'POST', credentials: 'same-origin', signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: route.model }),
    });
    const status = await readResponse(result, 'Model startup');
    if (status.status === 'ready') {
      window.dispatchEvent(new CustomEvent('local-model-status-changed'));
      return;
    }
    if (status.status === 'error') throw new Error(status.error || 'Model startup failed.');
    if (status.status !== 'starting') throw new Error('Model startup returned an unknown state.');
    onProgress(status.elapsed || 0);
    signal.throwIfAborted();
    await new Promise((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(signal.reason); };
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 1000);
      signal.addEventListener('abort', abort, { once: true });
    });
  }
  throw new Error('Model startup timed out. Check Cookbook for details.');
}
