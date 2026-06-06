// js/views/dashboard.js

import * as store from '../store.js';
import * as utils from '../utils.js';

const CONTAINER = 'view-dashboard';

export function initDashboard() {
  // Subscribe to the data keys this view cares about
  store.subscribe('findings',     () => render());
  store.subscribe('apps',         () => render());
  store.subscribe('fleet_average',() => render());
  store.subscribe('status',       () => render());
  store.subscribe('change_summary',() => render());

  // Initial render (may show empty state)
  render();
}

function render() {
  const el = document.getElementById(CONTAINER);
  if (!el) return;

  const findings    = store.get('findings') || [];
  const apps        = store.get('apps') || {};
  const fleet       = store.get('fleet_average') || 0;
  const status      = store.get('status') || { state: 'idle' };
  const changeSummary = store.get('change_summary') || { first_run: true };

  if (findings.length === 0 && status.state === 'idle') {
    el.innerHTML = _renderEmptyState();
    return;
  }

  el.innerHTML = `
    ${_renderChangeBanner(changeSummary)}
    ${_renderSeverityCards(findings)}
    <div class="dashboard-grid">
        ${_renderFleetScore(fleet)}
        ${_renderAppScores(apps)}
    </div>
    ${_renderLatestFindings(findings.slice(0, 10))}
  `;
}

function _renderSeverityCards(findings) {
  const counts = { CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0, INFO:0 };
  findings.forEach(f => { if (f.severity in counts) counts[f.severity]++; });

  return `<div class="severity-cards">
    ${Object.entries(counts).map(([sev, n]) => `
      <div class="sev-card sev-${sev.toLowerCase()}" onclick="window.location.hash='#/issues?severity=${sev}'">
        <div class="sev-count">${n}</div>
        <div class="sev-label">${sev}</div>
      </div>
    `).join('')}
  </div>`;
}

function _renderFleetScore(fleet) {
    return `
    <div class="fleet-score-section">
        <h3>Fleet Health</h3>
        <div class="fleet-score-card ${utils.scoreClass(fleet)}">
            <div class="fleet-score-value">${Math.round(fleet)}%</div>
            <div class="fleet-score-label">Global Average</div>
        </div>
    </div>
    `;
}

function _renderAppScores(apps) {
  const entries = Object.entries(apps);
  if (!entries.length) return '';

  return `<div class="app-scores-section">
    <h3>App Health</h3>
    <div class="app-score-grid">
      ${entries.map(([name, data]) => `
        <div class="app-score-card ${utils.scoreClass(data.score)}">
          <div class="app-score-value">${Math.round(data.score)}
            <span class="score-unit">%</span>
          </div>
          <div class="app-score-name">${utils.escapeHtml(name)}</div>
          ${data.is_hub ? '<span class="hub-badge">HUB</span>' : ''}
        </div>
      `).join('')}
    </div>
  </div>`;
}

function _renderLatestFindings(findings) {
  if (!findings.length) return '';
  return `<div class="latest-findings">
    <h3>Latest Findings</h3>
    <table class="findings-table">
      <thead>
        <tr><th></th><th>Scanner</th><th>Title</th><th>File</th><th>Line</th></tr>
      </thead>
      <tbody>
        ${findings.map(f => `
          <tr class="finding-row" data-id="${f.id}">
            <td>${utils.severityBadge(f.severity)}</td>
            <td><span class="scanner-badge">${f.scanner}</span></td>
            <td>${utils.escapeHtml(f.title)}</td>
            <td class="file-cell">${utils.escapeHtml(f.file)}</td>
            <td>${f.line}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>`;
}

function _renderEmptyState() {
  return `<div class="empty-state">
    <div class="empty-icon">⚡</div>
    <h2>No audit has run yet</h2>
    <p>Click <strong>▶ Run</strong> to start your first audit.</p>
  </div>`;
}

function _renderChangeBanner(summary) {
  if (summary.first_run || !summary.new_violations) return '';
  return `<div class="change-banner">
    <strong>${summary.new_violations} new violations</strong> since last run.
    ${summary.resolved_violations} resolved.
  </div>`;
}
