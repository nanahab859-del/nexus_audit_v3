import { startRun, cancelRun } from './api.js';
import { getState, getFilteredFindings } from './state.js';

let activeIndex = 0;
let items = [];

const commands = [
  { name: 'Run Audit', icon: '▶', action: () => startRun() },
  { name: 'Cancel Audit', icon: '⏹', action: () => cancelRun() },
  { name: 'Open Settings', icon: '⚙', action: () => document.getElementById('btn-settings').click() },
  { name: 'Toggle Theme', icon: '🌙', action: () => document.getElementById('btn-theme').click() },
];

export function initCommandPalette() {
  const palette = document.getElementById('command-palette');
  const input = palette.querySelector('.palette-input');
  const list = palette.querySelector('.palette-list');

  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      palette.classList.toggle('active');
      input.focus();
    }
    if (e.key === 'Escape') {
      palette.classList.remove('active');
    }
  });

  input.addEventListener('input', () => {
    const query = input.value.toLowerCase();
    const findings = getFilteredFindings().slice(0, 5).map(f => ({
      name: `${f.title} (${f.file}:${f.line})`,
      icon: severityIcon(f.severity),
      action: () => { location.hash = `#/issues?id=${f.id}`; }
    }));
    items = [...commands.filter(c => c.name.toLowerCase().includes(query)), ...findings];
    renderList();
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { activeIndex = Math.min(activeIndex + 1, items.length - 1); renderList(); }
    else if (e.key === 'ArrowUp') { activeIndex = Math.max(activeIndex - 1, 0); renderList(); }
    else if (e.key === 'Enter' && items[activeIndex]) {
      items[activeIndex].action();
      palette.classList.remove('active');
      input.value = '';
    }
  });

  function renderList() {
    list.innerHTML = items.map((item, idx) => `
      <div class="palette-item ${idx === activeIndex ? 'active' : ''}" data-index="${idx}">
        <span>${item.icon}</span> <span>${item.name}</span>
      </div>
    `).join('');
    list.querySelectorAll('.palette-item').forEach(el => {
      el.addEventListener('click', () => {
        const idx = parseInt(el.dataset.index);
        if (items[idx]) items[idx].action();
        palette.classList.remove('active');
        input.value = '';
      });
    });
  }

  function severityIcon(sev) {
    const map = { CRITICAL:'🔴', HIGH:'🟠', MEDIUM:'🟡', LOW:'🟢', INFO:'🔵' };
    return map[sev] || '⚪';
  }
}
