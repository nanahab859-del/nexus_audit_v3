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

/** Alias so settings.js can call api.saveSettings() */
export const saveSettings = updateSettings;

export function getConfig() {
  return _fetch('/api/config');
}

export function saveConfig(config) {
  return _fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export function getConfigYaml() {
  return fetch('/api/config/yaml').then(r => r.text());
}

export function validateConfig(config) {
  return _fetch('/api/config/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
}

export function getScannerStatus() {
  return _fetch('/api/scanners/status');
}

export function getScanners() {
  return _fetch('/api/scanners');
}

export function reloadRegistry() {
  return _fetch('/api/registry/reload', { method: 'POST' });
}

export function getCapabilities() {
  return _fetch('/api/capabilities');
}

/**
 * Install a scanner via pip. Returns a ReadableStream of NDJSON lines.
 * Each line: { line: "...", done: false } or { done: true, status: "ok"|"error" }
 */
export async function installScanner(name, onLine) {
  const res = await fetch('/api/scanners/install', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const raw of lines) {
      if (!raw.trim()) continue;
      try { onLine(JSON.parse(raw)); } catch { /* ignore parse errors */ }
    }
  }
}

export function registerCustomScanner(name, executable, output_pattern) {
  return _fetch('/api/scanners/custom', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, executable, output_pattern }),
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

export function pingProject(path) {
  return _fetch('/api/project/ping', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
}

export function validateRemote(url, branch, auth_type, token_env) {
  return _fetch('/api/project/validate-remote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, branch, auth_type, token_env }),
  });
}
