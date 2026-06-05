// js/store.js

const _initial = {
  // Server state (from /api/status and SSE)
  status:        { state: 'idle', job_id: null },

  // Audit data (from /api/data)
  metadata:      { job_id: null, project_path: '', started_at: null,
                   finished_at: null, total_findings: 0, total_violations: 0, git_context: {} },
  findings:      [],   // flat list, all findings
  apps:          {},   // { app_name: AppScore }
  fleet_average: 0.0,
  coupling:      { apps: [], matrix: [], details: {} },
  dna:           {},
  config_health: [],
  dependencies:  [],
  recommendations: [],
  change_summary: { first_run: true, new_violations: 0, resolved_violations: 0, score_deltas: {} },
  rules_summary:  [],

  // UI state (local only, not from server)
  activeView:    'dashboard',
  filters:       { severity: null, scanner: null, category: null, search: '' },
  selectedFinding: null,
  scanProgress:  {},   // { scanner_name: { percent, file } }
  logLines:      [],   // last 200 entries
  settings:      {},
};

const _subscribers = new Map();   // key → Set<callback>

function _notify(key) {
  const subs = _subscribers.get(key);
  if (subs) {
    subs.forEach(cb => {
      try {
        cb(_state[key]);
      } catch (err) {
        console.error(`Error in subscriber for ${key}:`, err);
      }
    });
  }
}

// The reactive state object — any property assignment triggers _notify
const _state = new Proxy({ ..._initial }, {
  set(target, key, value) {
    target[key] = value;
    _notify(key);
    return true;
  }
});

// Public API
export function get(key) { return _state[key]; }

export function set(key, value) {
  _state[key] = value;   // triggers Proxy setter → _notify
}

export function subscribe(key, callback) {
  if (!_subscribers.has(key)) _subscribers.set(key, new Set());
  _subscribers.get(key).add(callback);
  // Immediate call with current value
  try {
    callback(_state[key]);
  } catch (err) {
    console.error(`Error in initial subscribe call for ${key}:`, err);
  }
  return () => _subscribers.get(key).delete(callback);  // returns unsubscribe fn
}

// Convenience setters
export function setAuditData(data) {
  // Called once when /api/data returns
  // Maps the exact JSON schema to store keys
  set('metadata',      data.metadata       || _initial.metadata);
  set('findings',      data.findings       || []);
  set('apps',          data.apps           || {});
  set('fleet_average', data.fleet_average  || 0);
  set('coupling',      data.coupling_matrix || { apps: [], matrix: [], details: {} });
  set('dna',           data.dna            || {});
  set('config_health', data.config_health  || []);
  set('dependencies',  data.dependency_scan || []);
  set('recommendations', data.recommendations || []);
  set('change_summary',  data.change_summary  || _initial.change_summary);
  set('rules_summary',   data.rules_summary   || []);
}

export function appendFinding(finding) {
  // Called when SSE 'finding' event arrives during a live scan
  set('findings', [...get('findings'), finding]);
}

export function setProgress(scanner, percent, file) {
  const current = { ...(get('scanProgress') || {}) };
  current[scanner] = { percent, file };
  set('scanProgress', current);
}

export function appendLog(level, message) {
  const lines = get('logLines');
  const updated = [...lines, { level, message, time: new Date().toISOString() }];
  set('logLines', updated.slice(-200));   // keep last 200
}

export function getFilteredFindings() {
  const filters = get('filters');
  return get('findings').filter(f => {
    if (filters.severity && f.severity !== filters.severity) return false;
    if (filters.scanner  && f.scanner  !== filters.scanner)  return false;
    if (filters.category && f.category !== filters.category) return false;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      if (!f.title.toLowerCase().includes(q) &&
          !f.file.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}
