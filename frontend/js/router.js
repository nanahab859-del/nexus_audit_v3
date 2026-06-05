// js/router.js
import * as store from './store.js';

const VIEWS = ['dashboard','issues','violations','security','dependencies',
               'recommendations','graph','trends','coupling','manifest',
               'config-health','settings'];

export function navigate(viewName) {
  if (!VIEWS.includes(viewName)) viewName = 'dashboard';
  store.set('activeView', viewName);

  // Show/hide view divs
  VIEWS.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) {
      el.classList.toggle('hidden', v !== viewName);
      el.classList.toggle('active', v === viewName);
    }
  });

  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });

  // Update URL hash without triggering hashchange if we're already there
  const currentHash = location.hash.replace('#/', '');
  if (currentHash !== viewName) {
      history.replaceState(null, '', `#/${viewName}`);
  }
}

export function init() {
  // Wire tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.view));
  });

  // Handle direct navigation or page refresh
  window.addEventListener('hashchange', () => {
    const view = location.hash.replace('#/', '') || 'dashboard';
    navigate(view);
  });

  // Initial view from URL hash
  const initial = location.hash.replace('#/', '') || 'dashboard';
  navigate(initial);
}
