import { getState, subscribe, getFilteredFindings } from './state.js';

function _renderSeverityCards(container, findings) {
  const counts = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0, INFO:0 };
  findings.forEach(f => { if (counts[f.severity] !== undefined) counts[f.severity]++; });
  const cards = Object.entries(counts).map(([sev, count]) =>
    `<div class="severity-card severity-${sev.toLowerCase()}">
       <div class="sev-label">${sev}</div>
       <div class="sev-count">${count}</div>
     </div>`).join('');
  container.querySelector('.dash-severity')?.remove();
  const section = document.createElement('div');
  section.className = 'dash-severity';
  section.innerHTML = `<div class="severity-grid">${cards}</div>`;
  container.appendChild(section);
}

function _renderHealthScores(container, healthScores) {
  container.querySelector('.dash-health')?.remove();
  const section = document.createElement('div');
  section.className = 'dash-health';
  const items = Object.entries(healthScores).map(([app, score]) => {
    const color = score >= 80 ? 'green' : (score >=50 ? 'amber' : 'red');
    return `<div class="health-row"><div class="health-name">${app}</div>
      <div class="health-bar"><div class="health-fill" style="width:${score}%;background:${color}"></div></div>
      <div class="health-score">${score}</div></div>`;
  }).join('');
  section.innerHTML = `<h3>App Health</h3>${items}`;
  container.appendChild(section);
}

function _renderFindingsTable(container, findings) {
  container.querySelector('.dash-findings')?.remove();
  const section = document.createElement('div');
  section.className = 'dash-findings';
  const rows = findings.slice(0,10).map(f =>
    `<tr class="finding-row" data-id="${f.id}">
       <td class="sev"><span class="badge sev-${f.severity.toLowerCase()}">${f.severity}</span></td>
       <td class="scanner">${f.scanner}</td>
       <td class="title">${f.title}</td>
       <td class="file">${f.file || ''}:${f.line || ''}</td>
     </tr>`).join('');
  section.innerHTML = `<h3>Latest Findings</h3><table class="findings-table"><thead><tr><th></th><th>Scanner</th><th>Title</th><th>File</th></tr></thead><tbody>${rows}</tbody></table>`;
  container.appendChild(section);
}

export function renderDashboard() {
  const container = document.getElementById('view-dashboard');
  if (!container) return;
  // Clear container but keep layout
  container.innerHTML = '';

  const state = getState();
  const findings = state.findings || [];
  const healthScores = state.healthScores || {};
  const status = state.status || { state: 'idle' };

  if ((findings.length === 0) && status.state === 'idle') {
    container.innerHTML = `<div style="text-align:center;padding:60px;">
      <h2 style="color:var(--text-secondary)">No audit has run yet</h2>
      <p style="margin-top:8px;color:var(--text-muted)">Click ▶ Run Audit to start</p>
    </div>`;
    return;
  }

  // Sections container
  const top = document.createElement('div');
  top.className = 'dashboard-top';
  container.appendChild(top);

  _renderSeverityCards(top, findings);
  _renderHealthScores(top, healthScores);
  _renderFindingsTable(container, getFilteredFindings());
}

export function initDashboard() {
  // Subscribe to relevant state keys
  subscribe('findings', renderDashboard);
  subscribe('healthScores', renderDashboard);
  subscribe('status', renderDashboard);
  // Initial render
  renderDashboard();
}
