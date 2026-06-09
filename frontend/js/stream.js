// js/stream.js
import * as api from './api.js';
import * as store from './store.js';

let _source = null;

export function initStream() {
  console.log('[Stream] Initializing SSE stream...');
  if (_source) {
    console.log('[Stream] Closing previous stream connection...');
    _source.close();
  }

  _source = api.openStream();
  console.log('[Stream] Stream object created, attaching event listeners...');

  _source.addEventListener('status', (e) => {
    try {
      const data = JSON.parse(e.data);
      console.log('[Stream:status] Received:', data);
      store.set('status', data);
    } catch (err) {
      console.error('[Stream:status] Failed to parse:', err);
    }
  });

  _source.addEventListener('progress', (e) => {
    try {
      const data = JSON.parse(e.data);
      console.log('[Stream:progress]', data.scanner + ':', data.percent + '%');
      store.setProgress(data.scanner, data.percent, data.file);
    } catch (err) {
      console.error('[Stream:progress] Failed to parse:', err);
    }
  });

  _source.addEventListener('log', (e) => {
    try {
      const data = JSON.parse(e.data);
      console.log('[Stream:log]', `[${data.level}]`, data.message);
      store.appendLog(data.level, data.message);
    } catch (err) {
      console.error('[Stream:log] Failed to parse:', err);
    }
  });

  _source.addEventListener('finding', (e) => {
    try {
      const data = JSON.parse(e.data);
      console.log('[Stream:finding] New finding received');
      store.appendFinding(data);
    } catch (err) {
      console.error('[Stream:finding] Failed to parse:', err);
    }
  });

  _source.onopen = () => {
    console.log('[Stream] ✓ Connected to SSE stream');
  };

  _source.onerror = (err) => {
    console.error('[Stream] ✗ Stream connection error:', err);
  };
}
