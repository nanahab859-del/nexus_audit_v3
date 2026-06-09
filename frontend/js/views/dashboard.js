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
  store.subscribe('scannerErrors', () => render());

  // Initial render (may show empty state)
  render();
}

function render() {
  try {
    const el = document.getElementById(CONTAINER);
    if (!el) {
      console.warn('[Dashboard] Container not found:', CONTAINER);
      return;
    }

    const findings    = store.get('findings') || [];
    const apps        = store.get('apps') || {};
    const fleet       = store.get('fleet_average') || 0;
    const status      = store.get('status') || { state: 'idle' };
    const changeSummary = store.get('change_summary') || { first_run: true };
    const scannerErrors = store.get('scannerErrors') || {};

    console.log('[Dashboard] Rendering with:', { findings: findings.length, status: status.state, scannerErrors: Object.keys(scannerErrors).length });

    if (findings.length === 0 && status.state === 'idle') {
      el.innerHTML = _renderEmptyState();
      return;
    }

    el.innerHTML = `
      ${_renderScannerWarnings(scannerErrors)}
      ${_renderChangeBanner(changeSummary)}
      ${_renderSeverityCards(findings)}
      <div class="dashboard-grid">
          ${_renderFleetScore(fleet)}
          ${_renderAppScores(apps)}
      </div>
      ${_renderLatestFindings(_getSortedByPriority(findings, 10))}
    `;
  } catch (err) {
    console.error('[Dashboard] Render error:', err);
    const el = document.getElementById(CONTAINER);
    if (el) {
      el.innerHTML = `<div style="color: red; padding: 2rem;"><h3>Error rendering dashboard</h3><p>${err.message}</p></div>`;
    }
  }
}

function _renderScannerWarnings(scannerErrors) {
  try {
    if (!scannerErrors || typeof scannerErrors !== 'object') {
      return '';
    }
    const errorList = Object.entries(scannerErrors);
    if (!errorList.length) return '';

    return `<div class="alert alert-warning" style="margin: 1rem 0; padding: 1rem; border-left: 4px solid #ffa500; background-color: #fff9f0; border-radius: 4px;">
      <h4 style="margin-top: 0; margin-bottom: 0.5rem;">⚠️ Some scanners unavailable</h4>
      <ul style="margin: 0; padding-left: 1.5rem;">
        ${errorList.map(([scanner, error]) => {
          const scannerStr = String(scanner || '');
          const errorStr = String(error || '');
          return `<li><code style="background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px;">${utils.escapeHtml(scannerStr)}</code>: ${utils.escapeHtml(errorStr)}</li>`;
        }).join('')}
      </ul>
    </div>`;
  } catch (err) {
    console.error('[Dashboard] Error rendering scanner warnings:', err);
    return '';
  }
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
  
  // Build dynamic header showing critical/high count
  const criticalHighCount = findings.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH').length;
  const headerText = criticalHighCount > 0
    ? `<h3>⚠️ Priority Findings <span style="font-size: 0.8em; color: #d9534f;">(${criticalHighCount} critical/high)</span></h3>`
    : `<h3>📋 Priority Findings</h3>`;
  
  return `<div class="latest-findings">
    ${headerText}
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

function _getSortedByPriority(findings, limit = 10) {
  const severityWeight = {
    CRITICAL: 5,
    HIGH:     4,
    MEDIUM:   3,
    LOW:      2,
    INFO:     1
  };

  // Within the same severity, these categories are more urgent
  const categoryWeight = {
    security:     5,
    architecture: 4,
    dependency:   3,
    quality:      2,
    performance:  1
  };

  console.log('[Dashboard] Sorting', findings.length, 'findings by priority (severity → category → line), limit:', limit);

  const sorted = [...findings].sort((a, b) => {
    // 1. Severity (descending - higher severity first)
    const sevDiff = (severityWeight[b.severity] || 0) - (severityWeight[a.severity] || 0);
    if (sevDiff !== 0) return sevDiff;

    // 2. Category urgency (descending - more urgent categories first)
    const catDiff = (categoryWeight[b.category] || 0) - (categoryWeight[a.category] || 0);
    if (catDiff !== 0) return catDiff;

    // 3. Earliest line number (ascending - core logic usually at top)
    const lineDiff = (a.line || 0) - (b.line || 0);
    if (lineDiff !== 0) return lineDiff;

    // 4. File path (ascending - deterministic ordering)
    return (a.file || '').localeCompare(b.file || '');
  });

  const result = sorted.slice(0, limit);
  console.log('[Dashboard] Top', limit, 'priority findings:', result.map(f => `${f.severity}/${f.category}/${f.scanner}`).join(', '));
  return result;
}
