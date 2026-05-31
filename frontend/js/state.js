const listeners = {};

let _state = {
  status: { state: 'idle', job_id: null },
  job: null,
  findings: [],
  scannerSummary: {},
  architecture: null,
  healthScores: {},
  ghostFiles: [],
  history: [],
  settings: null,
  activeView: 'dashboard',
  filters: { severity: null, scanner: null, file: null, search: '' },
  selectedFinding: null,
  scanProgress: {},
  logLines: []
};

function _notify(key) {
  if (listeners[key]) listeners[key].forEach(fn => fn(_state[key]));
}

export function subscribe(key, fn) {
  if (!listeners[key]) listeners[key] = [];
  listeners[key].push(fn);
  return { key, fn }; // token to unsubscribe
}

export function unsubscribe(token) {
  const arr = listeners[token.key];
  if (arr) listeners[token.key] = arr.filter(f => f !== token.fn);
}

function _update(changes) {
  Object.assign(_state, changes);
  Object.keys(changes).forEach(key => _notify(key));
}

export function setDataFromJob(jobData) {
  const findings = [];
  const scannerSummary = {};
  for (const sr of (jobData.scan_results || [])) {
    findings.push(...sr.findings);
    const dur = sr.finished_at && sr.started_at ?
      (new Date(sr.finished_at) - new Date(sr.started_at)) / 1000 : null;
    scannerSummary[sr.scanner] = { count: sr.findings.length, duration: dur };
  }
  _update({
    job: jobData,
    findings,
    scannerSummary,
    architecture: jobData.architecture || null,
    healthScores: jobData.architecture?.health_scores || {},
    ghostFiles: jobData.architecture?.ghost_files || []
  });
}

export function setStatus(s) { _update({ status: s }); }
export function setSettings(s) { _update({ settings: s }); }
export function setHistory(h) { _update({ history: h }); }
export function setActiveView(v) { _update({ activeView: v }); }

export function setProgress(scanner, percent, file) {
  const sp = { ..._state.scanProgress };
  sp[scanner] = { percent, file };
  _update({ scanProgress: sp });
}

export function appendLog(level, message) {
  const lines = [..._state.logLines, `[${new Date().toLocaleTimeString()}] ${message}`].slice(-100);
  _update({ logLines: lines });
}

export function selectFinding(f) { _update({ selectedFinding: f }); }

export function getState() { return { ..._state }; }

export function getFilteredFindings() {
  let list = _state.findings.slice();
  const f = _state.filters;
  if (f.severity) list = list.filter(i => i.severity === f.severity);
  if (f.scanner)  list = list.filter(i => i.scanner === f.scanner);
  if (f.file)     list = list.filter(i => i.file.includes(f.file));
  if (f.search)   list = list.filter(i =>
    i.title.toLowerCase().includes(f.search.toLowerCase()) ||
    i.file.toLowerCase().includes(f.search.toLowerCase()));
  const order = { CRITICAL:0, HIGH:1, MEDIUM:2, LOW:3, INFO:4 };
  list.sort((a, b) => (order[a.severity] || 5) - (order[b.severity] || 5));
  return list;
}
