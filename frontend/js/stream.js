// js/stream.js
import * as api from './api.js';
import * as store from './store.js';

let _source = null;

export function initStream() {
  if (_source) {
    _source.close();
  }

  _source = api.openStream();

  _source.addEventListener('status', (e) => {
    try {
      const data = JSON.parse(e.data);
      store.set('status', data);
    } catch (err) {
      console.error('Failed to parse SSE status event:', err);
    }
  });

  _source.addEventListener('progress', (e) => {
    try {
      const data = JSON.parse(e.data);
      store.setProgress(data.scanner, data.percent, data.file);
    } catch (err) {
      console.error('Failed to parse SSE progress event:', err);
    }
  });

  _source.addEventListener('log', (e) => {
    try {
      const data = JSON.parse(e.data);
      store.appendLog(data.level, data.message);
    } catch (err) {
      console.error('Failed to parse SSE log event:', err);
    }
  });

  _source.addEventListener('finding', (e) => {
    try {
      const data = JSON.parse(e.data);
      store.appendFinding(data);
    } catch (err) {
      console.error('Failed to parse SSE finding event:', err);
    }
  });

  _source.onopen = () => {
    console.log('SSE Stream connected');
  };

  _source.onerror = (err) => {
    console.error('SSE Stream error:', err);
  };
}
