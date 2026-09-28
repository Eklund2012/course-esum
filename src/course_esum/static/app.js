/**
 * Course Evaluation Summarizer — Client Application
 *
 * Communicates with the FastAPI backend via REST + SSE.
 * Keeps things simple: vanilla JS, no build step.
 */

// ──────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────
const API_BASE = '/api/v1/evaluations';
const API_KEY  = 'dev-secret-key-12345';          // matches dev .env default
const DEMO_DATA = {
  course_name_and_code: "Fundamentals in AI and Optimization Techniques (DVAE23)",
  positive_summary: [
    "Discussions around the subject and varied teaching methods were highly valued by the students",
    "The examination tasks are considered to have been well connected to the content of the teaching",
    "Students felt that the course forced them to allocate time and that they generally prepared well"
  ],
  critique_summary: [
    "The feedback provided was not perceived to be helpful enough in the later evaluations",
    "The NPS result (Net Promoter Score) dropped drastically from +100 to strongly negative figures (-66.67 and -80)",
    "Student engagement/involvement in lectures and seminars decreased and the course structure's support functions deteriorated slightly"
  ],
  workload: "Too high",
  trend_over_time: "The course started in 2023 with very good results and high satisfaction. During 2024, grades and satisfaction dropped sharply (partly explained by the course coordinator being on sick leave)..."
};

// ──────────────────────────────────────────────
// DOM References
// ──────────────────────────────────────────────
const tabCode     = document.getElementById('tab-code');
const tabUpload   = document.getElementById('tab-upload');
const panelCode   = document.getElementById('panel-code');
const panelUpload = document.getElementById('panel-upload');

const courseCodeInput  = document.getElementById('course-code');
const maxReportsSlider = document.getElementById('max-reports');
const maxReportsVal    = document.getElementById('max-reports-val');
const langSelect       = document.getElementById('output-lang');
const langSelectUpload = document.getElementById('output-lang-upload');

const uploadZone  = document.getElementById('upload-zone');
const fileInput   = document.getElementById('file-input');
const fileListEl  = document.getElementById('file-list');

const submitBtn     = document.getElementById('submit-btn');
const submitBtnText = document.getElementById('submit-btn-text');
const demoCheckbox  = document.getElementById('demo-mode');
const statusBar     = document.getElementById('status-bar');
const resultsSection = document.getElementById('results-section');

let currentTab = 'code';   // 'code' | 'upload'
let selectedFiles = [];    // File[]
let isProcessing = false;

// ──────────────────────────────────────────────
// Tab Switching
// ──────────────────────────────────────────────
tabCode.addEventListener('click', () => switchTab('code'));
tabUpload.addEventListener('click', () => switchTab('upload'));

function switchTab(tab) {
  currentTab = tab;
  const isCode = tab === 'code';

  tabCode.classList.toggle('tab-switcher__btn--active', isCode);
  tabUpload.classList.toggle('tab-switcher__btn--active', !isCode);
  tabCode.setAttribute('aria-selected', isCode);
  tabUpload.setAttribute('aria-selected', !isCode);

  panelCode.hidden  = !isCode;
  panelUpload.hidden = isCode;
}

// ──────────────────────────────────────────────
// Range Slider
// ──────────────────────────────────────────────
maxReportsSlider.addEventListener('input', () => {
  maxReportsVal.textContent = maxReportsSlider.value;
});

// ──────────────────────────────────────────────
// File Upload
// ──────────────────────────────────────────────
fileInput.addEventListener('change', () => {
  addFiles(fileInput.files);
  fileInput.value = '';                   // allow re-selecting same file
});

uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('upload-zone--dragover');
});

uploadZone.addEventListener('dragleave', () => {
  uploadZone.classList.remove('upload-zone--dragover');
});

uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('upload-zone--dragover');
  addFiles(e.dataTransfer.files);
});

function addFiles(fileList) {
  for (const f of fileList) {
    if (f.name.toLowerCase().endsWith('.pdf') && !selectedFiles.some(x => x.name === f.name)) {
      selectedFiles.push(f);
    }
  }
  renderFileChips();
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  renderFileChips();
}

function renderFileChips() {
  fileListEl.innerHTML = selectedFiles.map((f, i) => `
    <span class="file-chip">
      📄 ${escapeHtml(f.name)}
      <button class="file-chip__remove" onclick="removeFile(${i})" aria-label="Remove ${escapeHtml(f.name)}">&times;</button>
    </span>
  `).join('');
}

// ──────────────────────────────────────────────
// Submit
// ──────────────────────────────────────────────
submitBtn.addEventListener('click', handleSubmit);

async function handleSubmit() {
  if (isProcessing) return;

  // Demo mode — instant render
  if (demoCheckbox.checked) {
    showResults(DEMO_DATA, []);
    return;
  }

  if (currentTab === 'code') {
    await submitCourseCode();
  } else {
    await submitFileUpload();
  }
}

// ──── Course Code Flow ────
async function submitCourseCode() {
  const code = courseCodeInput.value.trim().toUpperCase();
  if (!code) {
    showStatus('error', 'Please enter a course code.');
    return;
  }

  setProcessing(true);
  showStatus('processing', `Submitting job for ${code}…`);

  try {
    const body = {
      course_code: code,
      output_language: langSelect.value,
      max_reports: parseInt(maxReportsSlider.value, 10)
    };

    const res = await apiFetch(`${API_BASE}/jobs/fetch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server responded with ${res.status}`);
    }

    const job = await res.json();
    await followJobStream(job.job_id);

  } catch (err) {
    showStatus('error', err.message);
    setProcessing(false);
  }
}

// ──── File Upload Flow ────
async function submitFileUpload() {
  if (selectedFiles.length === 0) {
    showStatus('error', 'Please upload at least one PDF.');
    return;
  }

  setProcessing(true);
  showStatus('processing', `Uploading ${selectedFiles.length} file(s)…`);

  try {
    const form = new FormData();
    selectedFiles.forEach(f => form.append('files', f));
    form.append('output_language', langSelectUpload.value);

    const res = await apiFetch(`${API_BASE}/jobs/upload`, {
      method: 'POST',
      body: form
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server responded with ${res.status}`);
    }

    const job = await res.json();
    await followJobStream(job.job_id);

  } catch (err) {
    showStatus('error', err.message);
    setProcessing(false);
  }
}

// ──────────────────────────────────────────────
// SSE Stream
// ──────────────────────────────────────────────
async function followJobStream(jobId) {
  showStatus('processing', 'Waiting for processing to start…');

  const evtSource = new EventSource(`${API_BASE}/jobs/${jobId}/stream?api_key=${encodeURIComponent(API_KEY)}`);

  // Because EventSource doesn't support custom headers natively,
  // we'll fall back to polling if SSE fails (e.g. if auth blocks it).
  let resolved = false;

  evtSource.addEventListener('status', (e) => {
    const data = JSON.parse(e.data);
    showStatus('processing', `Status: ${data.status}`);
  });

  evtSource.addEventListener('update', (e) => {
    const data = JSON.parse(e.data);

    if (data.status === 'COMPLETED' && data.data) {
      resolved = true;
      evtSource.close();
      showStatus('success', 'Analysis complete!');
      showResults(data.data, data.data.reports_analyzed || []);
      setProcessing(false);
      return;
    }

    if (data.status === 'FAILED') {
      resolved = true;
      evtSource.close();
      showStatus('error', data.error || 'Job failed.');
      setProcessing(false);
      return;
    }

    if (data.message) {
      showStatus('processing', data.message);
    }
  });

  evtSource.onerror = () => {
    evtSource.close();
    if (!resolved) {
      // Fallback: poll
      pollJobStatus(jobId);
    }
  };
}

async function pollJobStatus(jobId) {
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    await sleep(2000);
    try {
      const res = await apiFetch(`${API_BASE}/jobs/${jobId}`);
      const job = await res.json();

      if (job.status === 'COMPLETED' && job.result) {
        showStatus('success', 'Analysis complete!');
        showResults(job.result, job.result.reports_analyzed || []);
        setProcessing(false);
        return;
      }

      if (job.status === 'FAILED') {
        showStatus('error', job.error_message || 'Job failed.');
        setProcessing(false);
        return;
      }

      showStatus('processing', `Processing… (${job.status})`);
    } catch {
      // ignore transient network errors, keep polling
    }
  }

  showStatus('error', 'Job timed out. Please try again.');
  setProcessing(false);
}

// ──────────────────────────────────────────────
// UI Helpers
// ──────────────────────────────────────────────
function setProcessing(flag) {
  isProcessing = flag;
  submitBtn.disabled = flag;
  submitBtnText.textContent = flag ? 'Processing…' : 'Generate Summary';
}

function showStatus(type, message) {
  let icon = '';
  let cardClass = '';

  switch (type) {
    case 'processing':
      icon = '<div class="status-spinner"></div>';
      cardClass = 'status-card--processing';
      break;
    case 'error':
      icon = '<span class="status-card__icon">⚠️</span>';
      cardClass = 'status-card--error';
      break;
    case 'success':
      icon = '<span class="status-card__icon">✅</span>';
      cardClass = 'status-card--success';
      break;
  }

  statusBar.innerHTML = `
    <div class="status-card ${cardClass}">
      ${icon}
      <span class="status-card__text">${escapeHtml(message)}</span>
    </div>
  `;
  statusBar.className = 'status-bar status-bar--visible';
}

function hideStatus() {
  statusBar.className = 'status-bar';
  statusBar.innerHTML = '';
}

// ──────────────────────────────────────────────
// Render Results
// ──────────────────────────────────────────────
function showResults(data, reports) {
  const positiveItems = (data.positive_summary || [])
    .map(t => `
      <li class="result-card__item">
        <span class="result-card__bullet" aria-hidden="true"></span>
        <span>${escapeHtml(t)}</span>
      </li>
    `).join('') || '<li class="result-card__item"><span>No information available.</span></li>';

  const negativeItems = (data.critique_summary || [])
    .map(t => `
      <li class="result-card__item">
        <span class="result-card__bullet" aria-hidden="true"></span>
        <span>${escapeHtml(t)}</span>
      </li>
    `).join('') || '<li class="result-card__item"><span>No information available.</span></li>';

  // Reports accordion
  let reportsHtml = '';
  if (reports && reports.length > 0) {
    const linkList = reports.map(label => `
      <div class="report-link">📎 ${escapeHtml(label)}</div>
    `).join('');

    reportsHtml = `
      <div class="reports-accordion" id="reports-accordion">
        <button class="reports-accordion__trigger" onclick="toggleAccordion()" type="button">
          <span>📄 Analyzed Reports (${reports.length})</span>
          <span class="reports-accordion__chevron">▼</span>
        </button>
        <div class="reports-accordion__content">
          ${linkList}
        </div>
      </div>
    `;
  }

  resultsSection.innerHTML = `
    <div class="results-header">
      <span class="results-header__badge">✦ Analysis Complete</span>
      <h2>${escapeHtml(data.course_name_and_code || 'Course Evaluation Summary')}</h2>
    </div>

    ${reportsHtml}

    <div class="results-grid">
      <div class="result-card result-card--positive">
        <div class="result-card__header">
          <span class="result-card__icon" aria-hidden="true">👍</span>
          <span class="result-card__title">Positive Aspects</span>
        </div>
        <ul class="result-card__list">${positiveItems}</ul>
      </div>
      <div class="result-card result-card--negative">
        <div class="result-card__header">
          <span class="result-card__icon" aria-hidden="true">👎</span>
          <span class="result-card__title">Areas for Improvement</span>
        </div>
        <ul class="result-card__list">${negativeItems}</ul>
      </div>
    </div>

    <div class="info-grid">
      <div class="info-card info-card--workload">
        <div class="info-card__header">
          <span class="info-card__icon" aria-hidden="true">⚖️</span>
          <span class="info-card__title">Workload</span>
        </div>
        <p class="info-card__body">${escapeHtml(data.workload || 'No information')}</p>
      </div>
      <div class="info-card info-card--trend">
        <div class="info-card__header">
          <span class="info-card__icon" aria-hidden="true">📈</span>
          <span class="info-card__title">Trend Over Time</span>
        </div>
        <p class="info-card__body">${escapeHtml(data.trend_over_time || 'No information')}</p>
      </div>
    </div>
  `;

  resultsSection.className = 'results-section results-section--visible';
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function toggleAccordion() {
  const el = document.getElementById('reports-accordion');
  el.classList.toggle('reports-accordion--open');
}

// ──────────────────────────────────────────────
// API Fetch Wrapper
// ──────────────────────────────────────────────
function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  headers['X-API-Key'] = API_KEY;
  return fetch(url, { ...options, headers });
}

// ──────────────────────────────────────────────
// Utilities
// ──────────────────────────────────────────────
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
