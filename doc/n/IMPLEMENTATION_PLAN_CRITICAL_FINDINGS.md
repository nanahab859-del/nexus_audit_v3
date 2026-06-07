# Implementation Plan: Critical Findings Priority in Dashboard

## Current Behavior
- Dashboard shows 10 **latest** findings (chronological order)
- Severity cards show counts of all 1,167 findings
- Critical/High priority issues might be buried in the list

## Proposed Behavior
- Dashboard shows 10 **most critical** findings (by severity level)
- Priority order: CRITICAL → HIGH → MEDIUM → LOW → INFO
- If there are 0 CRITICAL issues, show HIGH issues, etc.
- Creates a visual "Critical Issue Panel" in dashboard

---

## Implementation Approach

### 1. Change the Findings Sorting Logic

**Current code in dashboard.js (line 48):**
```javascript
${_renderLatestFindings(findings.slice(0, 10))}
```

**Proposed new code:**
```javascript
${_renderLatestFindings(_getSortedByPriority(findings, 10))}
```

### 2. Add New Sorting Function

**Add this function to dashboard.js:**

```javascript
function _getSortedByPriority(findings, limit = 10) {
  // Define severity priority (higher number = more critical)
  const severityPriority = {
    'CRITICAL': 5,
    'HIGH': 4,
    'MEDIUM': 3,
    'LOW': 2,
    'INFO': 1
  };

  // Sort findings by severity priority (descending)
  // Then by line number (ascending) as tiebreaker
  const sorted = [...findings].sort((a, b) => {
    const aPriority = severityPriority[a.severity] || 0;
    const bPriority = severityPriority[b.severity] || 0;
    
    if (aPriority !== bPriority) {
      return bPriority - aPriority;  // Higher priority first
    }
    
    // Tiebreaker: earlier line numbers first
    return (a.line || 0) - (b.line || 0);
  });

  return sorted.slice(0, limit);
}
```

### 3. Modify Table Header to Show "Priority Findings"

**Current header:**
```html
<h3>Latest Findings</h3>
```

**Proposed header:**
```html
<h3>⚠️ Critical Priority Findings</h3>
```

Or with dynamic count:
```javascript
const criticalCount = findings.filter(f => f.severity === 'CRITICAL').length;
const highCount = findings.filter(f => f.severity === 'HIGH').length;
const title = criticalCount > 0 
  ? `⚠️ Critical Issues (${criticalCount} total)`
  : highCount > 0
    ? `⚠️ High Issues (${highCount} total)`
    : '📋 Latest Findings';
```

---

## Complete Code Change Example

### Current dashboard.js (lines 40-50):

```javascript
    el.innerHTML = `
      ${_renderScannerWarnings(scannerErrors)}
      ${_renderChangeBanner(changeSummary)}
      ${_renderSeverityCards(findings)}
      <div class="dashboard-grid">
          ${_renderFleetScore(fleet)}
          ${_renderAppScores(apps)}
      </div>
      ${_renderLatestFindings(findings.slice(0, 10))}
    `;
```

### Proposed Change:

```javascript
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
```

### Add New Function (at end of file before empty):

```javascript
function _getSortedByPriority(findings, limit = 10) {
  // Define severity priority (higher number = more critical)
  const severityPriority = {
    'CRITICAL': 5,
    'HIGH': 4,
    'MEDIUM': 3,
    'LOW': 2,
    'INFO': 1
  };

  console.log('[Dashboard] Sorting', findings.length, 'findings by priority, limit:', limit);

  // Sort findings by severity priority (descending)
  // Then by line number (ascending) as tiebreaker
  const sorted = [...findings].sort((a, b) => {
    const aPriority = severityPriority[a.severity] || 0;
    const bPriority = severityPriority[b.severity] || 0;
    
    if (aPriority !== bPriority) {
      return bPriority - aPriority;  // Higher priority first
    }
    
    // Tiebreaker: earlier line numbers first
    return (a.line || 0) - (b.line || 0);
  });

  const result = sorted.slice(0, limit);
  console.log('[Dashboard] Top', limit, 'critical findings:', result.map(f => `${f.severity}/${f.scanner}`).join(', '));
  return result;
}
```

---

## Current Data Analysis

Based on your audit:
- **CRITICAL:** 0 findings
- **HIGH:** 0 findings  
- **MEDIUM:** 0 findings
- **LOW:** 1,167 findings (971 from vulture, 196 from bandit)
- **INFO:** 0 findings

**Expected Result with This Change:**
- Dashboard will show 10 LOW severity findings (top priority available)
- Since there are no CRITICAL/HIGH issues, LOW severity issues are most important
- Table header will show the priority level
- Users can see the most important issues at a glance

---

## Visual Example

### Before (Current):
```
Latest Findings
┌─────────────────────────────────────────────────┐
│ LOW  │ vulture │ Dead code detected │ file.py:7 │
│ LOW  │ vulture │ Dead code detected │ file.py:5 │
│ LOW  │ bandit  │ Hardcoded password │ test.py:34│
│ ...  │ ...     │ ...                │ ...       │
│ LOW  │ vulture │ Dead code detected │ file.py:20│
└─────────────────────────────────────────────────┘
(10 random LOW issues)
```

### After (Proposed):
```
⚠️ Critical Priority Findings
┌─────────────────────────────────────────────────┐
│ LOW  │ vulture │ Dead code detected │ file.py:4 │
│ LOW  │ vulture │ Dead code detected │ file.py:5 │
│ LOW  │ bandit  │ Hardcoded password │ test.py:34│
│ ...  │ ...     │ ...                │ ...       │
│ LOW  │ vulture │ Dead code detected │ file.py:14│
└─────────────────────────────────────────────────┘
(10 most critical LOW issues - sorted)
```

---

## Benefits

✅ **Immediate visibility** of the most critical issues
✅ **Automatic priority sorting** - no manual intervention needed
✅ **Scalable** - works with any severity mix (CRITICAL, HIGH, MEDIUM, LOW, INFO)
✅ **Scanner-agnostic** - works for both vulture and bandit findings
✅ **Users see worst issues first** - better decision making
✅ **Console logging** - can debug sorting logic if needed

---

## Implementation Steps

1. ✅ Add `_getSortedByPriority()` function to dashboard.js
2. ✅ Change line 48 from `.slice(0, 10)` to `_getSortedByPriority(findings, 10)`
3. ✅ Optional: Update header from "Latest Findings" to "Critical Priority Findings"
4. ✅ Test in browser - should show 10 findings sorted by severity
5. ✅ Verify sorting in console logs

---

## Questions for You

1. Should the header dynamically show "CRITICAL Issues" when there are critical issues, or always show "Critical Priority Findings"?
2. Should we show more than 10 if some severities have very few issues? (e.g., if only 2 CRITICAL, show 8 HIGH to reach 10 total?)
3. Should we add visual indicators (red/orange/yellow icons) next to severity badges?

---

## No Breaking Changes
- ✅ No changes to data structure
- ✅ No changes to API
- ✅ No changes to backend
- ✅ Only UI/sorting logic change
- ✅ Easy to revert if needed
