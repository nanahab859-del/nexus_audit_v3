export async function fetchJSON(path, options = {}) {
  try {
    const res = await fetch(path, options);
    if (!res.ok) {
      throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error(`fetchJSON Error on ${path}:`, err);
    throw err;
  }
}

export async function getStatus() {
  return fetchJSON('/api/status');
}

export async function getData() {
  return fetchJSON('/api/data');
}

export async function startRun() {
  return fetchJSON('/api/run', { method: 'POST' });
}

export async function cancelRun() {
  return fetchJSON('/api/cancel', { method: 'POST' });
}

export async function getSettings() {
  return fetchJSON('/api/settings');
}

export async function saveSettings(data) {
  return fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
}

export async function getHistory() {
  return fetchJSON('/api/history');
}

export function openStream(handlers) {
  const source = new EventSource('/api/stream');
  
  if (handlers.onStatus) {
    source.addEventListener('status', e => {
      try { handlers.onStatus(JSON.parse(e.data)); } catch (err) {}
    });
  }
  
  if (handlers.onProgress) {
    source.addEventListener('progress', e => {
      try { handlers.onProgress(JSON.parse(e.data)); } catch (err) {}
    });
  }
  
  if (handlers.onLog) {
    source.addEventListener('log', e => {
      try { handlers.onLog(JSON.parse(e.data)); } catch (err) {}
    });
  }
  
  if (handlers.onFinding) {
    source.addEventListener('finding', e => {
      try { handlers.onFinding(JSON.parse(e.data)); } catch (err) {}
    });
  }
  
  source.onerror = (e) => {
    if (handlers.onError) handlers.onError(e);
    source.close();
  };
  
  return source;
}
