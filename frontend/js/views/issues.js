// frontend/js/views/issues.js

import * as store from '../store.js';
import * as utils from '../utils.js';

const CONTAINER = 'view-issues';

// Helpers not present in utils.js
const truncate = (str, n) => (str && str.length > n) ? str.slice(0, n - 1) + '…' : str;
const filename = (path) => path ? path.split('/').pop() : '';

export function initIssues() {
  // Subscribe to findings and filters
  store.subscribe('findings', () => render());
  store.subscribe('filters', () => render());
  
  // Initial render
  render();
}

function render() {
  const el = document.getElementById(CONTAINER);
  if (!el) return;

  const findings = store.get('findings') || [];
  const filtered = store.getFilteredFindings() || [];
  const filters = store.get('filters') || { severity: null, scanner: null, category: null, search: '' };

  // Sort: CRITICAL, HIGH, MEDIUM, LOW, INFO
  const severityOrder = { 'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3, 'INFO': 4 };
  const sorted = [...filtered].sort((a, b) => {
    const orderA = severityOrder[a.severity] ?? 99;
    const orderB = severityOrder[b.severity] ?? 99;
    if (orderA !== orderB) return orderA - orderB;
    return (a.file || '').localeCompare(b.file || '') || (a.line - b.line);
  });

  const uniqueScanners = [...new Set(findings.map(f => f.scanner))].filter(Boolean).sort();

  el.innerHTML = `
    <div class="filter-bar">
      <div class="filter-bar__count">
        Showing ${sorted.length} of ${findings.length} findings
      </div>
      <div class="filter-bar__filters">
        <select id="filter-severity">
          <option value="">All Severities</option>
          <option value="CRITICAL" ${filters.severity === 'CRITICAL' ? 'selected' : ''}>CRITICAL</option>
          <option value="HIGH" ${filters.severity === 'HIGH' ? 'selected' : ''}>HIGH</option>
          <option value="MEDIUM" ${filters.severity === 'MEDIUM' ? 'selected' : ''}>MEDIUM</option>
          <option value="LOW" ${filters.severity === 'LOW' ? 'selected' : ''}>LOW</option>
          <option value="INFO" ${filters.severity === 'INFO' ? 'selected' : ''}>INFO</option>
        </select>

        <select id="filter-scanner">
          <option value="">All Scanners</option>
          ${uniqueScanners.map(s => `
            <option value="${s}" ${filters.scanner === s ? 'selected' : ''}>${s}</option>
          `).join('')}
        </select>

        <select id="filter-category">
          <option value="">All Categories</option>
          <option value="security" ${filters.category === 'security' ? 'selected' : ''}>security</option>
          <option value="quality" ${filters.category === 'quality' ? 'selected' : ''}>quality</option>
          <option value="architecture" ${filters.category === 'architecture' ? 'selected' : ''}>architecture</option>
          <option value="dependency" ${filters.category === 'dependency' ? 'selected' : ''}>dependency</option>
        </select>

        <input type="text" id="filter-search" placeholder="Search title or file..." value="${filters.search || ''}">
      </div>
    </div>

    ${sorted.length === 0 ? `
      <div class="empty-state" style="padding-top: var(--space-12)">
        <p>No findings match the current filters.</p>
      </div>
    ` : `
      <table class="findings-table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Scanner</th>
            <th>Title</th>
            <th>File</th>
            <th style="text-align: right">Line</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${sorted.map(f => `
            <tr class="finding-row">
              <td>${utils.severityBadge(f.severity)}</td>
              <td><span class="badge badge-idle">${f.scanner}</span></td>
              <td title="${utils.escapeHtml(f.title)}">${utils.escapeHtml(truncate(f.title, 60))}</td>
              <td title="${utils.escapeHtml(f.file)}" class="file-cell">${utils.escapeHtml(filename(f.file))}</td>
              <td style="text-align: right; font-family: var(--font-mono)">${f.line}</td>
              <td><span class="badge badge-idle" style="opacity: 0.8">${f.fix_status || 'open'}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `}
  `;

  // Attach event listeners
  el.querySelector('#filter-severity').onchange = (e) => {
    store.set('filters', { ...store.get('filters'), severity: e.target.value || null });
  };
  el.querySelector('#filter-scanner').onchange = (e) => {
    store.set('filters', { ...store.get('filters'), scanner: e.target.value || null });
  };
  el.querySelector('#filter-category').onchange = (e) => {
    store.set('filters', { ...store.get('filters'), category: e.target.value || null });
  };
  el.querySelector('#filter-search').oninput = (e) => {
    store.set('filters', { ...store.get('filters'), search: e.target.value });
  };
}
