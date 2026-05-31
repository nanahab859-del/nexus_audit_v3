const BASE = 'http://127.0.0.1:8421';

class ApiError extends Error {
  constructor(status, body) {
    super(body.message || `HTTP ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new ApiError(res.status, err);
  }
  return res.json();
}

export async function getStatus()          { return request('GET', '/api/status'); }
export async function getData()            { return request('GET', '/api/data'); }
export async function getHistory()         { return request('GET', '/api/history'); }
export async function getHistoryItem(id)   { return request('GET', `/api/history/${id}`); }
export async function getSettings()        { return request('GET', '/api/settings'); }
export async function saveSettings(data)   { return request('POST', '/api/settings', data); }
export async function startRun()           { return request('POST', '/api/run'); }
export async function cancelRun()          { return request('POST', '/api/cancel'); }

export function openStream(handlers) {
  const es = new EventSource(`${BASE}/api/stream`);
  es.addEventListener('status',   e => handlers.onStatus?.(JSON.parse(e.data)));
  es.addEventListener('progress', e => handlers.onProgress?.(JSON.parse(e.data)));
  es.addEventListener('log',      e => handlers.onLog?.(JSON.parse(e.data)));
  es.addEventListener('finding',  e => handlers.onFinding?.(JSON.parse(e.data)));
  es.onerror = e => handlers.onError?.(e);
  return es;
}
