// frontend/js/dashboard.js
export function renderFindingsTable(data) {
    const scanResults = data.scan_results || [];
    let allFindings = [];
    for (const sr of scanResults) {
        const scanner = sr.scanner;
        for (const f of sr.findings || []) {
            allFindings.push({ ...f, scanner });
        }
    }
    if (allFindings.length === 0) return '<p>No findings.</p>';

    let html = '<table><thead><tr><th>Severity</th><th>Scanner</th><th>Title</th><th>File</th><th>Line</th></tr></thead><tbody>';
    for (const f of allFindings) {
        html += `<tr>
            <td>${f.severity}</td>
            <td>${f.scanner}</td>
            <td>${f.title}</td>
            <td>${f.file}</td>
            <td>${f.line}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    return html;
}
