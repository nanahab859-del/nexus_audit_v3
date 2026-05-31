export function severityClass(severity) {
  return `severity-${severity.toLowerCase()}`;
}

export function severityIcon(severity) {
  const map = { CRITICAL:'🔴', HIGH:'🟠', MEDIUM:'🟡', LOW:'🟢', INFO:'🔵' };
  return map[severity] || '⚪';
}

export function relativeTime(isoString) {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diff = (now - then) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

export function truncate(str, max = 80) {
  return str.length <= max ? str : str.slice(0, max) + '…';
}

export function escapeHtml(str) {
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}
