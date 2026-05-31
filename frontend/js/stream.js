import { openStream } from './api.js';
import { setStatus, setProgress, appendLog, setDataFromJob, getState } from './state.js';
import { getData } from './api.js';

export function initStream() {
  const es = openStream({
    onStatus(data) {
      setStatus(data);
      if (data.state === 'completed') {
        // Reload full data when job completes
        getData().then(job => {
          if (job) setDataFromJob(job);
        }).catch(() => {});
      }
    },
    onProgress(data) {
      setProgress(data.scanner, data.percent, data.file || '');
    },
    onLog(data) {
      appendLog(data.level, data.message);
    },
    onFinding(data) {
      // Immediate injection: we'll just reload data for simplicity
      getData().then(job => {
        if (job) setDataFromJob(job);
      });
    },
    onError(e) {
      console.warn('SSE error (auto-reconnect)', e);
    }
  });
  return es;
}
