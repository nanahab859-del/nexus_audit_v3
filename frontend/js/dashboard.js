import { getState, getFilteredFindings, setActiveView } from './state.js';
import { navigate } from './router.js';

export function renderDashboard() {
  const state = getState();
  const container = document.getElementById('view-dashboard');
  if (!container) return;

  let html = '';

  // --- Severity Cards ---
  const findings = getFilteredFindings();
  const sevCounts = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0, INFO:0 };
  findings.forEach(f => { if (sevCounts[f.severity] !== undefined) sevCounts[f.severity]++; });
  html += '<div class="metrics-grid">';
  for (const [sev, count] of Object.entries(sevCounts)) {
    const color = severityColor(sev);
    html += `<div class="metric-card" onclick="navigate('#/issues?severity=${sev}')">
      <div class="metric-label">${sev}</div>
      <div class="metric-value" style="color:${color}">${count}</div>
    </div>`;
  }
  html += '</div>';

  // --- Scanner Summary Badges ---
  html += '<div style="margin:12px 0;">';
  Object.entries(state.scannerSummary).forEach(([name, info]) => {
    const dur = info.duration ? ` (${info.duration.toFixed(1)}s)` : '';
    html += `<span class="badge badge-info" style="margin-right:6px;">${name}: ${info.count}${dur}</span>`;
  });
  html += '</div>';

  // --- Architecture Health Cards ---
  if (Object.keys(state.healthScores).length > 0) {
    html += '<h3>🏥 Application Health</h3><div class="app-grid">';
    for (const [app, score] of Object.entries(state.healthScores)) {
      const color = score >= 80 ? 'var(--status-healthy)' : score >= 50 ? 'var(--status-warning)' : 'var(--status-critical)';
      html += `<div class="app-card">
        <div class="app-name">${app}</div>
        <div class="app-score" style="color:${color}">${score}%</div>
        <div class="score-bar"><div class="score-fill" style="width:${score}%;background:${color}"></div></div>
      </div>`;
    }
    html += '</div>';
  }

  // --- Ghost Files ---
  if (state.ghostFiles && state.ghostFiles.length > 0) {
    html += '<details class="ghost-card"><summary>👻 Ghost Files (' + state.ghostFiles.length + ')</summary><ul>';
    state.ghostFiles.forEach(f => html += `<li>${f}</li>`);
    html += '</ul></details>';
  }

  // --- Latest Findings Table ---
  const latest = findings.slice(0, 10);
  if (latest.length > 0) {
    html += '<h3 style="margin-top:20px;">Latest Findings</h3><table><thead><tr><th>Severity</th><th>Scanner</th><th>Title</th><th>File</th><th>Line</th></tr></thead><tbody>';
    latest.forEach(f => {
      html += `<tr onclick="navigate('#/issues?id=${f.id}')" style="cursor:pointer;">
        <td><span class="badge badge-${f.severity.toLowerCase()}">${f.severity}</span></td>
        <td>${f.scanner}</td>
        <td>${f.title}</td>
        <td>${f.file}</td>
        <td>${f.line}</td>
      </tr>`;
    });
    html += '</tbody></table>';
    html += `<p style="margin-top:8px;"><a href="#/issues">View all →</a></p>`;
  } else if (state.status.state === 'idle') {
    html += '<div class="text-center" style="margin-top:40px;"><p>No audit has run yet.</p><p>Click <strong>▶ Run Audit</strong> to start.</p></div>';
  }

  container.innerHTML = html;
}

function severityColor(sev) {
  const map = {
    CRITICAL: 'var(--status-critical)',
    HIGH: 'var(--status-warning)',
    MEDIUM: '#3b82f6',
    LOW: 'var(--status-healthy)',
    INFO: '#5b9bd5'
  };
  return map[sev] || '#fff';
}

// Expose navigation helper globally for onclick in innerHTML
window.navigate = (hash) => { location.hash = hash; };
