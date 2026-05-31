// frontend/js/stream.js
export function connectStream(onProgress, onLog, onStatus) {
    const es = new EventSource('/api/stream');
    es.addEventListener('progress', (e) => {
        const d = JSON.parse(e.data);
        onProgress(d.scanner, d.percent, d.file);
    });
    es.addEventListener('log', (e) => {
        const d = JSON.parse(e.data);
        onLog(d.level, d.message);
    });
    es.addEventListener('status', (e) => {
        const d = JSON.parse(e.data);
        onStatus(d.state, d.job_id);
        if (d.state === 'completed') es.close();
    });
    es.onerror = () => {
        // Reconnect automatically (EventSource does this by default)
    };
    return es;
}
