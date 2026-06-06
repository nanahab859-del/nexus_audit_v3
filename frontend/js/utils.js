// js/utils.js

export function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

export function scoreClass(score) {
  if (score >= 90) return 'score-excellent';
  if (score >= 75) return 'score-good';
  if (score >= 50) return 'score-fair';
  return 'score-poor';
}

export function severityBadge(severity) {
  const sev = String(severity).toUpperCase();
  return `<span class="badge badge-${sev.toLowerCase()}">${sev}</span>`;
}
