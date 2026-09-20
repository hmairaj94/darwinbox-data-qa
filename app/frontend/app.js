let sessionId = null;
let activeChart = null;
const uploadForm = document.querySelector('#upload-form');
const queryForm = document.querySelector('#query-form');
const status = document.querySelector('#status');

function setBusy(form, busy) {
  form.querySelector('button').disabled = busy;
}

function showError(target, error) {
  target.textContent = error instanceof Error ? error.message : String(error);
}

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault(); setBusy(uploadForm, true);
  const target = document.querySelector('#dataset'); target.textContent = 'Profiling files…';
  const body = new FormData();
  for (const file of document.querySelector('#files').files) body.append('files', file);
  try {
    const response = await fetch('/api/upload_file', {method: 'POST', body});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Upload failed');
    sessionId = data.session_id;
    target.textContent = data.tables.map((table) => {
      const location = table.source_range ? ` · ${table.source_range}` : '';
      const confidence = table.detection_confidence < 1
        ? ` · ${Math.round(table.detection_confidence * 100)}% detection confidence`
        : '';
      const warnings = table.warnings.length ? `\n  ⚠ ${table.warnings.join(' ')}` : '';
      return `${table.name} (${table.rows} rows)${location}${confidence}${warnings}`;
    }).join('\n');
    document.querySelector('#query-card').classList.remove('disabled');
  } catch (error) { showError(target, error); } finally { setBusy(uploadForm, false); }
});

queryForm.addEventListener('submit', async (event) => {
  event.preventDefault(); setBusy(queryForm, true); status.textContent = 'Analysing…';
  document.querySelector('#answer').hidden = true;
  try {
    const question = document.querySelector('#question').value;
    const response = await fetch(`/api/sessions/${sessionId}/query`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Analysis failed');
    status.textContent = `Completed in ${data.attempts} query attempt${data.attempts === 1 ? '' : 's'}.`;
    document.querySelector('#answer-text').textContent = data.answer;
    document.querySelector('#sql').textContent = data.sql;
    document.querySelector('#answer').hidden = false;
    renderTable(data.columns, data.rows); renderChart(data.chart, data.rows);
  } catch (error) { showError(status, error); } finally { setBusy(queryForm, false); }
});

function renderTable(columns, rows) {
  const table = document.querySelector('#result-table'); table.replaceChildren();
  if (!columns.length) return;
  const head = table.createTHead().insertRow();
  columns.forEach(column => { const th = document.createElement('th'); th.textContent = column; head.appendChild(th); });
  const body = table.createTBody();
  rows.forEach(row => { const tr = body.insertRow(); columns.forEach(column => { tr.insertCell().textContent = row[column] ?? ''; }); });
}

function renderChart(spec, rows) {
  const wrap = document.querySelector('.chart-wrap');
  if (activeChart) activeChart.destroy();
  if (!spec) { wrap.hidden = true; return; }
  wrap.hidden = false;
  activeChart = new Chart(document.querySelector('#chart'), {
    type: spec.type,
    data: {labels: rows.map(row => row[spec.x]), datasets: [{label: spec.y, data: rows.map(row => row[spec.y]), backgroundColor: '#19714a99', borderColor: '#19714a'}]},
    options: {responsive: true, maintainAspectRatio: false, plugins: {title: {display: true, text: spec.title}}}
  });
}
