// js/views/placeholder.js

import * as utils from '../utils.js';

const placeholders = {
  violations: {
    title: 'Violations',
    description: 'Violation summaries and remediation guidance appear here after a scan.',
  },
  security: {
    title: 'Security',
    description: 'Security view pending implementation; this page will show security findings and trends.',
  },
  dependencies: {
    title: 'Dependencies',
    description: 'Dependency analysis and risk will appear here after scan results are available.',
  },
  recommendations: {
    title: 'AI Fixes',
    description: 'AI-driven remediation suggestions appear here after a completed audit.',
  },
  graph: {
    title: 'Graph',
    description: 'Application dependency graphs will render here in future updates.',
  },
  trends: {
    title: 'Trends',
    description: 'Audit trends and history will display here over time.',
  },
  coupling: {
    title: 'Coupling',
    description: 'Coupling metrics and app relationships will be shown here once scan data is loaded.',
  },
  manifest: {
    title: 'Manifest',
    description: 'Manifest and package metadata will be available here after the audit runs.',
  },
  'config-health': {
    title: 'Config',
    description: 'Configuration health checks are displayed here once the audit loads settings and rules.',
  },
  settings: {
    title: 'Settings',
    description: 'Settings can be viewed and updated here. This view is a placeholder until full settings support is implemented.',
  }
};

export function initPlaceholderViews() {
  Object.entries(placeholders).forEach(([viewName, meta]) => {
    const el = document.getElementById(`view-${viewName}`);
    if (!el) return;
    el.innerHTML = renderPlaceholder(meta.title, meta.description);
  });
}

function renderPlaceholder(title, description) {
  return `
    <section class="placeholder-page">
      <div class="placeholder-card">
        <h2>${utils.escapeHtml(title)}</h2>
        <p>${utils.escapeHtml(description)}</p>
      </div>
    </section>
  `;
}
