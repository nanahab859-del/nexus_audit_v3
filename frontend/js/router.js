import { setActiveView, subscribe, getState } from './state.js';

function parseHash() {
  const raw = location.hash.slice(1) || '/';
  const [path, query] = raw.split('?');
  const params = {};
  if (query) {
    query.split('&').forEach(pair => {
      const [k, v] = pair.split('=');
      params[k] = v || true;
    });
  }
  return { path, params };
}

export function navigate(hash) {
  location.hash = hash;
}

function handleRoute() {
  const { path, params } = parseHash();
  if (path === '/' || path === '/dashboard') setActiveView('dashboard');
  else if (path === '/issues') setActiveView('issues');
  else if (path === '/history') setActiveView('history');
  else setActiveView('dashboard');
}

window.addEventListener('hashchange', handleRoute);
window.addEventListener('DOMContentLoaded', handleRoute);
