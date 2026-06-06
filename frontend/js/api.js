// js/api.js

export class ApiError extends Error {
  constructor(status, body) {
    super(`API Error ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function _fetch(url, options = {}) {
  const start = performance.now();
  console.log('[API] Calling', options.method || 'GET', url);
  try {
    const res = await fetch(url, options);
    const duration = performance.now() - start;
    console.log('[API] Response for', url, `status=${res.status} (${duration.toFixed(0)}ms)`);
    
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      console.error('[API] Error response:', res.status, body);
      throw new ApiError(res.status, body);
    }
    if (res.status === 204) {
      console.log('[API] ✓', url, '(204 No Content)');
      return null;
    }
    const data = await res.json();
    console.log('[API] ✓', url, 'returned data');
    return data;
  } catch (err) {
    console.error('[API] ✗ Exception:', err.message);
    throw err;
  }
}

export function getStatus() {
  console.log('[API.getStatus] Called');
  return _fetch('/api/status');
}

export function getData() {
  console.log('[API.getData] Called');
  return _fetch('/api/data');
}

export function getSettings() {
  console.log('[API.getSettings] Called');
  return _fetch('/api/settings');
}

export function updateSettings(settings) {
  console.log('[API.updateSettings] Called with:', Object.keys(settings));
  return _fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
}

export function startRun(fast = false) {
  console.log('[API.startRun] Called, fast=' + fast);
  return _fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fast }),
  });
}

export function cancelRun() {
  console.log('[API.cancelRun] Called');
  return _fetch('/api/cancel', { method: 'POST' });
}

export function openStream() {
  // EventSource doesn't support custom headers easily for Last-Event-ID
  // so we let the browser handle it automatically via standard EventSource
  return new EventSource('/api/stream');
}
