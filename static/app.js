/* ==========================================================================
   Celina's Job Toolkit — v3: Fully Autonomous SSE Client
   Uses fetch + ReadableStream instead of EventSource to avoid
   auto-reconnect issues.
   ========================================================================== */

let allPeople = [];
let currentJob = {};

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('smart-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') go();
    });
    renderHistory();
});

// ---- Main flow ----
async function go() {
    const input = document.getElementById('smart-input').value.trim();
    if (!input) return showToast('Enter a job URL, "Title at Company", or a company name.');

    const openai_key = document.getElementById('openai-key').value.trim();
    const hunter_key = document.getElementById('hunter-key').value.trim();

    resetUI();
    show('pipeline');
    show('results');
    document.getElementById('go-btn').disabled = true;
    document.getElementById('go-btn').textContent = 'Working...';

    try {
        const resp = await fetch('/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ input, openai_key, hunter_key }),
        });
        const { job_id, error } = await resp.json();
        if (error) { showToast(error); resetBtn(); return; }

        await streamSSE(job_id);
    } catch (err) {
        console.error('Pipeline error:', err);
        showToast('Something went wrong. Try again.');
    } finally {
        resetBtn();
    }
}

// ---- SSE via fetch + ReadableStream (no auto-reconnect) ----
async function streamSSE(jobId) {
    const resp = await fetch(`/stream/${jobId}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse complete SSE messages from buffer
        const parts = buffer.split('\n\n');
        buffer = parts.pop(); // keep incomplete part

        for (const part of parts) {
            if (!part.trim()) continue;
            let eventType = 'message';
            let dataStr = '';

            for (const line of part.split('\n')) {
                if (line.startsWith('event:')) {
                    eventType = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    dataStr += line.slice(5).trim();
                }
            }

            if (!dataStr) continue;

            try {
                const data = JSON.parse(dataStr);
                handleEvent(eventType, data);
            } catch (err) {
                console.warn('Failed to parse SSE data:', dataStr, err);
            }

            if (eventType === 'done_stream') return;
        }
    }
}

function handleEvent(type, data) {
    try {
        switch (type) {
            case 'status':
                setStep(data.step, data.message);
                break;

            case 'job_info':
                currentJob = data;
                renderJobSummary(data);
                show('section-job');
                break;

            case 'email_verification':
                renderMxBadge(data);
                show('section-mx');
                break;

            case 'person':
                allPeople.push(data);
                appendPersonCard(data);
                document.getElementById('people-counter').textContent = allPeople.length;
                show('section-people');
                break;

            case 'company_research':
                renderCompanyResearch(data);
                show('section-research');
                break;

            case 'cover_letter':
                document.getElementById('cover-text').textContent = data.text;
                show('section-cover');
                break;

            case 'email_patterns':
                renderEmailPatterns(data);
                show('section-email-patterns');
                break;

            case 'interview_prep':
                renderInterviewPrep(data);
                show('section-interview');
                break;

            case 'done':
                saveHistory(data);
                finishPipeline(data);
                break;

            case 'app_error':
                if (data.message) showToast(data.message);
                document.getElementById('pipeline').classList.add('hidden');
                break;
        }
    } catch (err) {
        console.error(`Error handling ${type} event:`, err, data);
    }
}

// ---- Pipeline progress ----
const STEP_ORDER = ['parsing', 'scraping', 'analyzing', 'searching', 'researching', 'generating'];

function setStep(step, message) {
    const idx = STEP_ORDER.indexOf(step);
    document.querySelectorAll('.step').forEach(el => {
        const sIdx = STEP_ORDER.indexOf(el.dataset.step);
        el.classList.remove('active', 'done');
        if (sIdx < idx) el.classList.add('done');
        else if (sIdx === idx) el.classList.add('active');
    });
    document.getElementById('pipeline-message').textContent = message || '';
}

function finishPipeline(data) {
    document.querySelectorAll('.step').forEach(el => {
        el.classList.remove('active');
        el.classList.add('done');
    });
    document.getElementById('pipeline-message').textContent =
        `Done! Found ${data.total_people} people at ${data.company}.`;
}

// ---- Render: Job Summary ----
function renderJobSummary(job) {
    document.getElementById('job-summary').innerHTML = `
        <div class="tag big">${esc(job.title)}</div>
        <div class="tag big">${esc(job.company)}</div>
        <div class="tag teal">${esc(job.department)}</div>
        <div class="tag teal">${esc(job.seniority)} level</div>
        ${(job.key_skills || []).slice(0, 6).map(s => `<div class="tag">${esc(s)}</div>`).join('')}
    `;
}

// ---- Render: MX badge ----
function renderMxBadge(mx) {
    document.getElementById('section-mx').innerHTML = mx.mx_valid
        ? `<div class="mx-badge valid">Email domain <strong>${esc(mx.domain)}</strong> verified (MX: ${esc(mx.mx_records[0] || '')})</div>`
        : `<div class="mx-badge invalid">Warning: <strong>${esc(mx.domain)}</strong> may not accept emails</div>`;
}

// ---- Render: Person Card ----
function appendPersonCard(person) {
    const msgs = person.personalized_messages || {};
    const conn = msgs.connection_request || {};
    const followup = msgs.followup_message || '';
    const emailSubj = msgs.email_subject || '';
    const emailBody = msgs.email_body || '';
    const emails = person.emails || [];
    const bestEmail = emails[0] || '';

    const icons = { recruiter: '🎯', hiring_manager: '👤', leadership: '⭐', hr: '🤝', team_member: '💼' };
    const labels = { recruiter: 'Recruiter', hiring_manager: 'Hiring Manager', leadership: 'Leadership', hr: 'HR', team_member: 'Team Member' };

    const mailto = bestEmail
        ? `mailto:${bestEmail}?subject=${encodeURIComponent(emailSubj)}&body=${encodeURIComponent(emailBody)}`
        : '';

    const card = document.createElement('div');
    card.className = 'person-card';
    card.innerHTML = `
        <div class="person-top">
            <div class="person-info">
                <div class="person-name">${icons[person.category] || '👤'} ${esc(person.name)}</div>
                <div class="person-meta">
                    <span class="category-badge ${esc(person.category)}">${esc(labels[person.category] || person.category)}</span>
                    ${person.job_title ? `<span class="person-title">${esc(person.job_title)}</span>` : ''}
                </div>
            </div>
            <div class="person-buttons">
                <a href="${esc(person.profile_url)}" target="_blank" rel="noopener" class="btn btn-linkedin">Open Profile</a>
                ${mailto ? `<a href="${mailto}" class="btn btn-email-send">Send Email</a>` : ''}
            </div>
        </div>

        ${emails.length > 0 ? `
        <div class="person-emails">
            ${emails.slice(0, 3).map((e, i) => `<span class="email-chip ${i === 0 ? 'primary' : ''}" onclick="copyText(this, '${esc(e)}')" title="Click to copy">${esc(e)}</span>`).join('')}
        </div>` : ''}

        <div class="person-messages">
            <div class="msg-block">
                <div class="msg-label">
                    Connection Request
                    <span class="char-count ${(conn.char_count || 0) <= 300 ? 'ok' : 'warn'}">${conn.char_count || 0}/300</span>
                </div>
                <div class="msg-text">${esc(conn.text || '')}</div>
                <button class="btn btn-copy-sm" onclick="copyText(this, ${escJ(conn.text || '')})">Copy</button>
            </div>
            <div class="msg-block">
                <div class="msg-label">Follow-up Message</div>
                <div class="msg-text pre">${esc(followup)}</div>
                <button class="btn btn-copy-sm" onclick="copyText(this, ${escJ(followup)})">Copy</button>
            </div>
        </div>
    `;

    document.getElementById('people-list').appendChild(card);
}

// ---- Render: Company Research ----
function renderCompanyResearch(data) {
    let html = '';

    if (data.news && data.news.length) {
        html += '<h3>Recent News</h3><div class="research-items">';
        data.news.forEach(n => {
            html += `<a href="${esc(n.url)}" target="_blank" rel="noopener" class="research-item">
                <div class="research-title">${esc(n.title)}</div>
                <div class="research-snippet">${esc(n.snippet)}</div>
            </a>`;
        });
        html += '</div>';
    }

    if (data.culture && data.culture.length) {
        html += '<h3>Culture & Reviews</h3><div class="research-items">';
        data.culture.forEach(c => {
            html += `<a href="${esc(c.url)}" target="_blank" rel="noopener" class="research-item">
                <div class="research-title">${esc(c.title)}</div>
                <div class="research-snippet">${esc(c.snippet)}</div>
            </a>`;
        });
        html += '</div>';
    }

    if (!html) html = '<p class="muted">No additional research found.</p>';
    document.getElementById('company-research').innerHTML = html;
}

// ---- Render: Email Patterns ----
function renderEmailPatterns(data) {
    document.getElementById('email-patterns').innerHTML = `
        <div class="patterns-grid">
            ${data.patterns.map(p => `
                <div class="pattern-item" onclick="copyText(this, '${esc(p.example)}')">
                    <code>${esc(p.pattern)}</code>
                    <span>${esc(p.example)}</span>
                </div>
            `).join('')}
        </div>
        <div class="email-note">${esc(data.note)}</div>
    `;
}

// ---- Render: Interview Prep ----
function renderInterviewPrep(prep) {
    document.getElementById('interview-prep').innerHTML = `
        <div class="prep-section">
            <h3>Key Skills</h3>
            <div class="skills-cloud">
                ${(prep.key_skills || []).map(s => `<span class="skill-tag">${esc(s)}</span>`).join('')}
                ${(prep.soft_skills || []).map(s => `<span class="skill-tag soft">${esc(s)}</span>`).join('')}
            </div>
        </div>
        <div class="prep-section">
            <h3>Likely Questions</h3>
            <ol class="prep-list">${(prep.tech_questions || []).map(q => `<li>${esc(q)}</li>`).join('')}</ol>
        </div>
        <div class="prep-section">
            <h3>Behavioral Questions</h3>
            <ol class="prep-list">${(prep.behavioral_questions || []).map(q => `<li>${esc(q)}</li>`).join('')}</ol>
        </div>
        <div class="prep-section">
            <h3>STAR Story Prompts</h3>
            <ol class="prep-list">${(prep.star_prompts || []).map(q => `<li>${esc(q)}</li>`).join('')}</ol>
        </div>
        <div class="prep-section">
            <h3>Questions to Ask Them</h3>
            <ol class="prep-list">${(prep.questions_to_ask || []).map(q => `<li>${esc(q)}</li>`).join('')}</ol>
        </div>
    `;
}

// ---- CSV Export ----
function downloadCSV() {
    if (!allPeople.length) return;
    const company = currentJob.company || 'company';
    let csv = 'Name,Title,Category,LinkedIn,Email 1,Email 2,Connection Message\n';
    allPeople.forEach(p => {
        const conn = (p.personalized_messages || {}).connection_request || {};
        csv += `"${csvEsc(p.name)}","${csvEsc(p.job_title)}","${csvEsc(p.category)}","${csvEsc(p.profile_url)}","${csvEsc((p.emails||[])[0]||'')}","${csvEsc((p.emails||[])[1]||'')}","${csvEsc(conn.text||'')}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `contacts_${company.replace(/\s+/g, '_')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

// ---- History ----
function saveHistory(data) {
    const history = JSON.parse(localStorage.getItem('celina_history') || '[]');
    history.unshift({
        input: document.getElementById('smart-input').value.trim(),
        title: data.title || '',
        company: data.company || '',
        people: data.total_people || 0,
        date: new Date().toLocaleDateString(),
    });
    if (history.length > 30) history.pop();
    localStorage.setItem('celina_history', JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    const history = JSON.parse(localStorage.getItem('celina_history') || '[]');
    const el = document.getElementById('history-list');
    if (!history.length) {
        el.innerHTML = '<p class="muted">No searches yet.</p>';
        return;
    }
    el.innerHTML = history.slice(0, 10).map(h => `
        <div class="history-item" onclick="document.getElementById('smart-input').value=${escJ(h.input)};go();">
            <div class="history-main">
                <strong>${esc(h.title || h.company || h.input)}</strong>
                ${h.company && h.title ? `<span class="muted">at ${esc(h.company)}</span>` : ''}
            </div>
            <div class="history-meta">
                <span>${h.people} people</span>
                <span>${esc(h.date)}</span>
            </div>
        </div>
    `).join('');
}

// ---- UI Helpers ----
function resetUI() {
    allPeople = [];
    currentJob = {};
    document.getElementById('people-list').innerHTML = '';
    document.getElementById('people-counter').textContent = '0';
    document.querySelectorAll('.result-section, .mx-badge-container').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.step').forEach(el => el.classList.remove('active', 'done'));
    document.getElementById('pipeline-message').textContent = 'Starting...';
}

function resetBtn() {
    document.getElementById('go-btn').disabled = false;
    document.getElementById('go-btn').textContent = 'Go';
}

function show(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('hidden');
}

function toggleAdvanced() {
    document.getElementById('advanced-content').classList.toggle('show');
    document.getElementById('adv-arrow').classList.toggle('open');
}

function toggleSection(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.toggle('hidden');
    const header = el.previousElementSibling;
    if (header) {
        const arrow = header.querySelector('.arrow');
        if (arrow) arrow.classList.toggle('open');
    }
}

// ---- Copy ----
function copyText(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent || btn.innerText;
        btn.classList.add('copied');
        if (btn.tagName === 'BUTTON') btn.textContent = 'Copied!';
        setTimeout(() => { btn.classList.remove('copied'); if (btn.tagName === 'BUTTON') btn.textContent = orig; }, 2000);
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
    });
}

// ---- Toast ----
function showToast(msg) {
    document.querySelectorAll('.toast').forEach(t => t.remove());
    const t = document.createElement('div');
    t.className = 'toast error';
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(() => t.classList.add('show'));
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 5000);
}

// ---- Utils ----
function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escJ(s) { return JSON.stringify(s || ''); }
function csvEsc(s) { return (s || '').replace(/"/g, '""'); }
