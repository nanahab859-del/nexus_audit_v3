// js/api.js

export class ApiError extends Error {
  constructor(status, body) {
    super(`API Error ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function _fetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return null;
  return res.json();
}

export function getStatus() {
  return _fetch('/api/status');
}

export function getData() {
  return _fetch('/api/data');
}

export function getSettings() {
  return _fetch('/api/settings');
}

export function updateSettings(settings) {
  return _fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
}

export function startRun(fast = false) {
  return _fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fast }),
  });
}

export function cancelRun() {
  return _fetch('/api/cancel', { method: 'POST' });
}

export function openStream() {
  // EventSource doesn't support custom headers easily for Last-Event-ID
  // so we let the browser handle it automatically via standard EventSource
  return new EventSource('/api/stream');
}
