import * as api from '../api.js';
import * as store from '../store.js';

let _el = null;
let _s = {};
let _caps = {};
let _onSave = null;
let _dirty = false;

let _testResult = null;
let _testError = null;
let _testLatency = null;
let _usage = null;
let _localOllamaModels = [];
let _advExpanded = false;

export function mountAI(element, settings, onSave) {
  _el = element;
  _s = deepClone(settings);
  _onSave = onSave;
  
  // Default values for new fields
  _s.ai_temperature = _s.ai_temperature ?? 0.7;
  _s.ai_max_tokens = _s.ai_max_tokens ?? 4096;
  _s.ai_timeout = _s.ai_timeout ?? 120;
  _s.ai_retry_enabled = _s.ai_retry_enabled ?? true;
  _s.ai_max_retries = _s.ai_max_retries ?? 3;
  _s.ai_context_limit = _s.ai_context_limit ?? 128000;
  _s.ai_data_scrubber = _s.ai_data_scrubber ?? true;
  _s.ai_prompt_shield = _s.ai_prompt_shield ?? true;
  _s.ai_key_pool = _s.ai_key_pool || [];

  api.getCapabilities().then(c => { 
    _caps = c || {}; 
    api.getAIUsage().then(u => {
      _usage = u;
      _render();
    }).catch(() => _render());
  }).catch(() => _render());
}

function _render() {
  if (!_el) return;

  const ai = _s.ai_enabled || false;
  const providers = _caps.ai_providers || [];
  const currentProviderId = _s.ai_provider || 'claude';
  const provider = providers.find(p => p.id === currentProviderId) || providers[0] || { models: [] };
  
  let models = provider.models.map(m => m.id);
  if (provider.id === 'ollama' && _localOllamaModels.length > 0) {
    models = _localOllamaModels;
  }
  
  let modelOptions = models.map(m => `<option value="${m}" ${_s.ai_model === m ? 'selected' : ''}>${m}</option>`).join('');
  modelOptions += `<option value="__custom__" ${!models.includes(_s.ai_model) && _s.ai_model ? 'selected' : ''}>✏ Enter custom model</option>`;

  let isCustomModel = !models.includes(_s.ai_model) && _s.ai_model;
  
  let currentModelObj = provider.models.find(m => m.id === _s.ai_model);
  let multimodalDisabled = currentModelObj && currentModelObj.multimodal !== true;

  _el.innerHTML = `
<div class="pv">
  <!-- Enable AI Toggle -->
  <div class="pv-section" style="padding:16px; background:var(--bg-elevated); border:1px solid var(--border-default); border-radius:6px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
    <div>
      <div style="font-size:var(--text-sm); font-weight:600">Enable AI</div>
      <div style="font-size:var(--text-xs); color:var(--text-muted)">Generate AI fix recommendations after each scan</div>
    </div>
    <label class="scanner-toggle">
      <input type="checkbox" class="scanner-toggle-input" id="ai-enabled-toggle" ${ai ? 'checked' : ''}>
      <span class="scanner-toggle__track"></span>
    </label>
  </div>

  <div id="ai-content-wrapper" style="transition: opacity 0.2s; ${ai ? '' : 'opacity:0.5; pointer-events:none'}">
    
    <!-- Provider & Model Card -->
    ${_section('Provider & Model', `
      <div class="pv-row2">
        ${_field('Provider', `
          <select class="pv-select" id="ai-provider">
            ${providers.map(p => `<option value="${p.id}" ${currentProviderId === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}
          </select>
        `)}
        ${_field('Model', `
          ${isCustomModel 
            ? `<input class="pv-input" id="ai-model-input" value="${esc(_s.ai_model)}" placeholder="Custom model name">` 
            : `<select class="pv-select" id="ai-model-select">${modelOptions}</select>`
          }
          ${provider.id === 'ollama' ? `<div style="margin-top:4px"><a href="#" id="ai-fetch-ollama" style="color:var(--accent-primary);font-size:11px">Fetch local models</a></div>` : ''}
        `)}
      </div>
      
      ${provider.id === 'custom' ? `
        <div class="pv-row1">
          ${_field('Endpoint URL', `<input class="pv-input pv-input--mono" id="ai-custom-endpoint" value="${esc(_s.ai_custom_endpoint)}" placeholder="https://api.openai.com/v1/chat/completions">`)}
        </div>
      ` : ''}

      <div class="pv-row1" style="margin-top:12px">
        ${_field('API Key (Primary)', `
          <div style="display:flex; gap:8px">
            <input class="pv-input pv-input--mono" id="ai-api-key" type="password"
                   placeholder="${_s.api_key ? '••••••••' : 'Enter API key'}" style="flex:1">
            <button class="pv-btn pv-btn--sm" id="btn-toggle-key" type="button" title="${_s.api_key ? 'Key is stored encrypted' : 'Show/hide key'}">👁</button>
            <button class="pv-btn pv-btn--sm pv-btn--ping" id="btn-test-conn" type="button">Test Connection</button>
          </div>
        `)}
      </div>

      <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--border-default)">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px">
          <label class="pv-label" style="margin:0">Key Pool (Rotates automatically if quota exceeded)</label>
          <button class="pv-btn pv-btn--sm" id="btn-add-key" ${_s.ai_key_pool.length >= 20 ? 'disabled' : ''}>+ Add Key</button>
        </div>
        <div id="key-pool-list" style="display:flex; flex-direction:column; gap:8px">
          ${_s.ai_key_pool.map((k, i) => `
            <div style="display:flex; gap:8px">
              <input class="pv-input pv-input--mono pool-key-input" type="password" value="${k==='***'?'••••••••':esc(k)}" data-idx="${i}" style="flex:1">
              <button class="pv-btn pv-btn--sm btn-toggle-pool" data-idx="${i}">👁</button>
              <button class="pv-btn pv-btn--sm pv-list-del btn-remove-pool" data-idx="${i}">×</button>
            </div>
          `).join('')}
        </div>
      </div>

      <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--border-default)">
        <label class="pv-check-label" style="margin-bottom:8px">
          <input type="checkbox" class="pv-check" id="ai-smart-routing" ${_s.ai_smart_routing ? 'checked' : ''}>
          Enable Smart Routing (Fallback to cheaper model on rate limits)
        </label>
        ${_s.ai_smart_routing ? `
          ${_field('Fallback Model', `<input class="pv-input" id="ai-fallback-model" value="${esc(_s.ai_fallback_model)}" placeholder="e.g. claude-haiku-4-3">`)}
        ` : ''}
      </div>
    `)}

    <!-- Advanced Parameters -->
    <div class="pv-section">
      <div class="pv-collapsible" style="margin-bottom:0">
        <button class="pv-collapse-btn" id="adv-toggle" style="width:100%; text-align:left; font-weight:600">
          Advanced Parameters <span class="pv-arrow" style="float:right">${_advExpanded ? '▲' : '▼'}</span>
        </button>
        <div id="adv-body" class="${_advExpanded ? '' : 'hidden'}" style="padding-top:16px">
          <div class="pv-row3">
            ${_field('Temperature', `<input type="number" class="pv-input" id="ai-temp" min="0" max="2" step="0.1" value="${_s.ai_temperature}">`)}
            ${_field('Max Tokens', `<input type="number" class="pv-input" id="ai-max-tokens" value="${_s.ai_max_tokens}">`)}
            ${_field('Context Limit', `<input type="number" class="pv-input" id="ai-context-limit" value="${_s.ai_context_limit}">`)}
          </div>
          <div class="pv-row3" style="margin-top:12px">
            ${_field('Timeout (s)', `<input type="number" class="pv-input" id="ai-timeout" value="${_s.ai_timeout}">`)}
            ${_field('Max Retries', `<input type="number" class="pv-input" id="ai-max-retries" value="${_s.ai_max_retries}" ${_s.ai_retry_enabled?'':'disabled'}>`)}
            ${_field('Retry Enabled', `<div style="padding-top:8px"><label class="pv-check-label"><input type="checkbox" id="ai-retry" ${_s.ai_retry_enabled?'checked':''}> Enabled</label></div>`)}
          </div>
          <div class="pv-row2" style="margin-top:12px">
            ${_field('API Version', `<input class="pv-input pv-input--mono" id="ai-api-version" value="${esc(_s.ai_api_version)}" placeholder="e.g. 2023-06-01">`)}
            ${_field('Organization ID', `<input class="pv-input pv-input--mono" id="ai-org-id" value="${esc(_s.ai_org_id)}" placeholder="org-123">`)}
          </div>
          <div style="margin-top:16px; padding-top:16px; border-top:1px solid var(--border-default)">
            <label class="pv-check-label" style="margin-bottom:8px; ${multimodalDisabled?'opacity:0.5':''}" title="${multimodalDisabled?'Your current model does not support multimodal':''}">
              <input type="checkbox" class="pv-check" id="ai-multimodal" ${_s.ai_multimodal_enabled ? 'checked' : ''} ${multimodalDisabled?'disabled':''}>
              Enable Multimodal (send images/diagrams to AI)
            </label>
            <div style="font-size:11px; color:var(--text-muted); margin-bottom:12px; margin-left:24px">Only check this if your model supports image inputs.</div>
            
            <label class="pv-check-label" style="margin-bottom:8px">
              <input type="checkbox" class="pv-check" id="ai-data-scrubber" ${_s.ai_data_scrubber ? 'checked' : ''}>
              PII Data Scrubber (Redact sensitive strings before sending)
            </label>
            <label class="pv-check-label">
              <input type="checkbox" class="pv-check" id="ai-prompt-shield" ${_s.ai_prompt_shield ? 'checked' : ''}>
              Prompt Injection Shield (Sanitize untrusted source code inputs)
            </label>
          </div>
        </div>
      </div>
    </div>

    <div class="pv-row2">
      <!-- Connection Status Card -->
      ${_section('Connection Status', `
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:12px">
          <div style="width:12px; height:12px; border-radius:50%; background:${_testResult === true ? '#2ea043' : (_testResult === false ? '#f85149' : '#8b949e')}"></div>
          <div style="font-weight:600; font-size:13px">${_testResult === true ? 'Connected' : (_testResult === false ? 'Failed' : 'Not tested')}</div>
        </div>
        ${_testLatency ? `<div style="font-size:12px; color:var(--text-muted); margin-bottom:4px">Latency: <strong>${_testLatency}ms</strong></div>` : ''}
        <div style="font-size:12px; color:var(--text-muted)">Provider: ${esc(currentProviderId)}</div>
        <div style="font-size:12px; color:var(--text-muted)">Model: ${esc(_s.ai_model)}</div>
        ${_testError ? `<div style="margin-top:8px; color:#f85149; font-size:11px; padding:8px; background:rgba(248,81,73,0.1); border-radius:4px">${esc(_testError)}</div>` : ''}
      `)}

      <!-- Usage & Cost Control -->
      ${_usage && !_usage.error ? `
        ${_section('Usage & Cost Control', `
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px">
            <div>
              <div style="font-size:11px; color:var(--text-muted)">Requests (Session)</div>
              <div style="font-size:18px; font-weight:600">${_usage.requests || 0}</div>
            </div>
            <div>
              <div style="font-size:11px; color:var(--text-muted)">Total Tokens</div>
              <div style="font-size:18px; font-weight:600">${_usage.total_tokens || 0}</div>
            </div>
            <div>
              <div style="font-size:11px; color:var(--text-muted)">Estimated Cost</div>
              <div style="font-size:18px; font-weight:600">$${(_usage.estimated_cost || 0).toFixed(4)}</div>
            </div>
          </div>
          ${_field('Monthly Budget Cap ($)', `<input type="number" class="pv-input pv-input--num" id="ai-budget" min="0" step="1" value="${_s.ai_budget_cap || 0}">`)}
        `)}
      ` : `<div style="flex:1"></div>`}
    </div>

  </div> <!-- end ai-content-wrapper -->

  <div class="pv-footer" style="padding-top:16px; margin-top:16px; border-top:1px solid var(--border-default); display:flex; justify-content:flex-end">
    <button class="pv-btn pv-btn--primary" id="ai-save">💾 Save Configuration</button>
  </div>
</div>
  `;

  _wire();
}

function _section(title, content) {
  return `<div class="pv-section">
    <div class="pv-section-title">${title}</div>
    <div class="pv-section-body">${content}</div>
  </div>`;
}

function _field(label, control) {
  return `<div class="pv-field">
    ${label ? `<label class="pv-label">${label}</label>` : ''}
    ${control}
  </div>`;
}

function _wire() {
  if (!_el) return;

  const g = id => _el.querySelector('#' + id);
  
  // Enable toggle
  g('ai-enabled-toggle')?.addEventListener('change', e => {
    _s.ai_enabled = e.target.checked;
    g('ai-content-wrapper').style.opacity = _s.ai_enabled ? '1' : '0.5';
    g('ai-content-wrapper').style.pointerEvents = _s.ai_enabled ? 'auto' : 'none';
    _dirty = true;
  });

  // Provider change
  g('ai-provider')?.addEventListener('change', e => {
    _s.ai_provider = e.target.value;
    const prov = (_caps.ai_providers || []).find(p => p.id === _s.ai_provider);
    if (prov && prov.default_model) {
      _s.ai_model = prov.default_model;
    }
    _dirty = true;
    _render();
  });

  // Model change
  g('ai-model-select')?.addEventListener('change', e => {
    if (e.target.value === '__custom__') {
      _s.ai_model = '';
    } else {
      _s.ai_model = e.target.value;
    }
    _dirty = true;
    _render();
  });

  g('ai-model-input')?.addEventListener('input', e => { _s.ai_model = e.target.value; _dirty = true; });
  g('ai-custom-endpoint')?.addEventListener('input', e => { _s.ai_custom_endpoint = e.target.value; _dirty = true; });
  
  // Fetch local models
  g('ai-fetch-ollama')?.addEventListener('click', async e => {
    e.preventDefault();
    try {
      const res = await api.getOllamaModels();
      if (res.available && res.models) {
        _localOllamaModels = res.models;
        if (!_s.ai_model && res.models.length > 0) _s.ai_model = res.models[0];
        _render();
      } else {
        alert('Could not fetch Ollama models. Is Ollama running?');
      }
    } catch(err) {
      alert('Error fetching Ollama models: ' + err.message);
    }
  });

  // Primary API Key toggle
  g('btn-toggle-key')?.addEventListener('click', () => {
    const inp = g('ai-api-key');
    if (inp) {
      if (inp.type === 'password' && inp.value === '' && _s.api_key) {
        // If it's empty but stored, we can't show it (it's ***). Just toggle type to let them type.
      }
      inp.type = inp.type === 'password' ? 'text' : 'password';
    }
  });
  g('ai-api-key')?.addEventListener('input', e => { _s.api_key = e.target.value; _dirty = true; });

  // Test Connection
  g('btn-test-conn')?.addEventListener('click', async () => {
    const btn = g('btn-test-conn');
    btn.disabled = true;
    btn.textContent = '⏳ Testing...';
    try {
      const keyVal = g('ai-api-key')?.value || (_s.api_key ? '***' : '');
      const res = await api.testAI(_s.ai_provider, _s.ai_model, keyVal, _s.ai_custom_endpoint);
      _testResult = res.success;
      _testLatency = res.latency_ms;
      _testError = res.error || null;
    } catch(err) {
      _testResult = false;
      _testError = err.message;
      _testLatency = null;
    }
    _render();
  });

  // Key Pool
  g('btn-add-key')?.addEventListener('click', () => {
    _s.ai_key_pool.push('');
    _dirty = true;
    _render();
  });
  _el.querySelectorAll('.pool-key-input').forEach(inp => {
    inp.addEventListener('input', e => {
      _s.ai_key_pool[parseInt(e.target.dataset.idx)] = e.target.value;
      _dirty = true;
    });
  });
  _el.querySelectorAll('.btn-remove-pool').forEach(btn => {
    btn.addEventListener('click', e => {
      _s.ai_key_pool.splice(parseInt(e.target.dataset.idx), 1);
      _dirty = true;
      _render();
    });
  });
  _el.querySelectorAll('.btn-toggle-pool').forEach(btn => {
    btn.addEventListener('click', e => {
      const inp = _el.querySelector(`.pool-key-input[data-idx="${e.target.dataset.idx}"]`);
      if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
    });
  });

  // Smart Routing
  g('ai-smart-routing')?.addEventListener('change', e => {
    _s.ai_smart_routing = e.target.checked;
    _dirty = true;
    _render();
  });
  g('ai-fallback-model')?.addEventListener('input', e => { _s.ai_fallback_model = e.target.value; _dirty = true; });

  // Advanced toggler
  g('adv-toggle')?.addEventListener('click', () => {
    _advExpanded = !_advExpanded;
    _render();
  });

  // Advanced simple fields
  const b = (id, key, type = 'text') => {
    g(id)?.addEventListener('input', e => {
      _s[key] = type === 'num' ? (Number(e.target.value)||0) : e.target.value;
      _dirty = true;
    });
  };
  b('ai-temp', 'ai_temperature', 'num');
  b('ai-max-tokens', 'ai_max_tokens', 'num');
  b('ai-timeout', 'ai_timeout', 'num');
  b('ai-context-limit', 'ai_context_limit', 'num');
  b('ai-max-retries', 'ai_max_retries', 'num');
  b('ai-api-version', 'ai_api_version');
  b('ai-org-id', 'ai_org_id');
  b('ai-budget', 'ai_budget_cap', 'num');

  const cb = (id, key) => {
    g(id)?.addEventListener('change', e => {
      _s[key] = e.target.checked;
      _dirty = true;
      if (id === 'ai-retry') _render(); // to disable/enable max_retries
    });
  };
  cb('ai-retry', 'ai_retry_enabled');
  cb('ai-multimodal', 'ai_multimodal_enabled');
  cb('ai-data-scrubber', 'ai_data_scrubber');
  cb('ai-prompt-shield', 'ai_prompt_shield');

  // Save button
  g('ai-save')?.addEventListener('click', async () => {
    const btn = g('ai-save');
    const origText = btn.textContent;
    btn.textContent = '⏳ Saving...';
    btn.disabled = true;
    try {
      await _onSave({ ..._s });
      store.set('settings', { ..._s });
    } finally {
      if (btn) {
        btn.textContent = origText;
        btn.disabled = false;
      }
    }
  });
}

function deepClone(obj) { return JSON.parse(JSON.stringify(obj)); }
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
