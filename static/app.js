/* ==========================================================================
   Celina's Job Toolkit — app.js (clean rewrite)
   LinkedIn-first approach. No email sending. Compact expandable cards.
   ========================================================================== */

let allPeople = [];
let currentJob = {};
let currentJobId = '';
let cid = 0;
let progressPct = 0;
let expandedCard = null;

/* ---- Init ---- */
document.addEventListener('DOMContentLoaded', () => {
    try {
        const input = document.getElementById('smart-input');
        if (input) {
            input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
            animatePlaceholder(input);
        }
        renderHistory();
        checkProfile();
        /* Auto-log LinkedIn profile clicks */
        document.addEventListener('click', e => {
            const link = e.target.closest('.btn-linkedin');
            if (link) {
                fetch('/api/activity', {method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({action_type: 'connected', company: currentJob.company || '', details: 'Opened LinkedIn profile'})
                }).catch(() => {});
            }
        });
    } catch (e) { console.error('Init error:', e); }
});

/* ---- Animated placeholder (typewriter — foundation/NGO examples) ---- */
function animatePlaceholder(el) {
    const examples = [
        'Program Coordinator at UNICEF',
        'Project Manager at Gates Foundation',
        'Communications Officer at MSF',
        'Grant Writer at Ford Foundation',
        'Operations Manager at Red Cross',
        'Policy Analyst at World Bank',
        'Fundraising Manager at Oxfam',
        'Program Officer at Open Society',
        'Advocacy Director at Amnesty International',
        'M&E Specialist at Save the Children',
    ];
    let idx = 0, charIdx = 0, deleting = false;

    function tick() {
        try {
            const text = examples[idx];
            if (!deleting) {
                el.setAttribute('placeholder', text.slice(0, charIdx));
                charIdx++;
                if (charIdx > text.length) {
                    deleting = true;
                    setTimeout(tick, 2000);
                    return;
                }
                setTimeout(tick, 50 + Math.random() * 30);
            } else {
                charIdx--;
                el.setAttribute('placeholder', text.slice(0, charIdx));
                if (charIdx === 0) {
                    deleting = false;
                    idx = (idx + 1) % examples.length;
                    setTimeout(tick, 300);
                    return;
                }
                setTimeout(tick, 25);
            }
        } catch (_) {}
    }
    tick();
}

/* ======================================================================
   Main flow
   ====================================================================== */

async function go() {
    const input = document.getElementById('smart-input').value.trim();
    if (!input) return toast('Type a job link or "Role at Company"');

    const desc = (document.getElementById('job-description') || {}).value || '';
    resetUI();
    setLoading(true);

    try {
        const r = await fetch('/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input, description: desc, lang: 'en' }),
        });
        const { job_id, error } = await r.json();
        if (error) { toast(error); setLoading(false); return; }
        await streamSSE(job_id);
    } catch (e) {
        console.error(e);
        toast('Something went wrong. Try again.');
    } finally {
        setLoading(false);
    }
}

/* ---- SSE Stream ---- */
async function streamSSE(id) {
    const r = await fetch(`/stream/${id}`);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop();
        for (const p of parts) {
            if (!p.trim()) continue;
            let type = '', dataLines = [];
            for (const line of p.split('\n')) {
                if (line.startsWith('event:')) type = line.slice(6).trim();
                else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
            }
            const data = dataLines.join('\n');
            if (!data) continue;
            try { handle(type, JSON.parse(data)); } catch (e) { console.warn('SSE parse error:', e); }
            if (type === 'done_stream') return;
        }
    }
}

/* ---- Event Handler ---- */
function handle(type, d) {
    try {
        switch (type) {
            case 'status': progress(d.step, d.message); break;
            case 'job_info': currentJob = d; break;
            case 'match_score': currentJob.match = d; break;
            case 'email_verification': currentJob.mx = d; break;

            case 'person':
                allPeople.push(d);
                addPersonCard(d);
                show('section-people');
                progressText(`Found ${allPeople.length} people...`);
                break;

            case 'company_research': renderResearch(d); show('section-intel'); break;
            case 'salary_data': renderSalary(d); show('section-intel'); break;
            case 'cover_letter': Q('cover-text').textContent = d.text; show('section-cover'); break;
            case 'email_patterns': renderPatterns(d); show('section-email-patterns'); break;
            case 'interview_prep': renderPrep(d); show('section-interview-all'); break;
            case 'interview_intel': renderIntel(d); show('section-interview-all'); break;
            case 'networking_strategy': renderStrategy(d); show('section-strategy'); break;

            case 'done':
                currentJobId = d.job_id || '';
                showEl('btn-pdf');
                showEl('btn-pdf-cover');
                buildSummary(d);
                show('section-actions');
                progressDone();
                saveHistory(d);
                break;

            case 'app_error':
                if (d.message) toast(d.message);
                Q('progress').classList.add('hidden');
                break;
        }
    } catch (e) { console.error('handle(' + type + '):', e); }
}

/* ======================================================================
   Progress
   ====================================================================== */

const STEPS = { parsing: 5, scraping: 15, analyzing: 20, searching: 55, researching: 75, generating: 92 };

function progress(step, msg) {
    const pct = STEPS[step] || progressPct;
    if (pct > progressPct) progressPct = pct;
    Q('progress-fill').style.width = progressPct + '%';
    Q('progress-text').textContent = msg;
    show('progress');
    show('results');
}

function progressText(t) {
    const el = Q('progress-text');
    if (el) el.textContent = t;
}

function progressDone() {
    Q('progress-fill').style.width = '100%';
    Q('progress-text').textContent = `Found ${allPeople.length} people. Done!`;
    setTimeout(() => { try { Q('progress').classList.add('hidden'); } catch (_) {} }, 2000);
}

/* ======================================================================
   Summary Card — LinkedIn-first, big number, copy-all CTA
   ====================================================================== */

function buildSummary(d) {
    const cats = {};
    allPeople.forEach(p => { cats[p.category] = (cats[p.category] || 0) + 1; });
    const names = {
        recruiter: 'Recruiters', hiring_manager: 'Managers',
        leadership: 'Leaders', hr: 'HR', team_member: 'Team',
    };
    const match = currentJob.match;

    let html = '<div class="sum-row">';

    /* Match score circle */
    if (match && match.score > 0) {
        const col = match.score >= 70 ? 'var(--green)' : match.score >= 50 ? 'var(--purple)' : 'var(--orange)';
        html += `<div class="sum-score" style="border-color:${col}">
            <span class="sum-pct" style="color:${col}">${match.score}%</span>
            <span class="sum-lbl">${h(match.label)}</span>
        </div>`;
    }

    /* Big count */
    html += `<div class="sum-count">
        <span class="sum-num">${d.total_people}</span>
        <span class="sum-lbl">people at <strong>${h(d.company)}</strong></span>
    </div>`;
    html += '</div>';

    /* Category tags */
    html += '<div class="sum-tags">';
    Object.entries(cats).forEach(([k, v]) => {
        html += `<span class="tag">${v} ${names[k] || k}</span>`;
    });
    if (currentJob.mx && currentJob.mx.mx_valid) {
        html += '<span class="tag green">Email verified</span>';
    }
    html += '</div>';

    /* Match details */
    if (match && match.score > 0) {
        html += '<div class="sum-match">';
        if (match.matched_skills?.length) {
            html += `<div class="match-row"><span class="match-good">Matched:</span> ${match.matched_skills.map(h).join(', ')}</div>`;
        }
        if (match.missing_skills?.length) {
            html += `<div class="match-row"><span class="match-miss">Add to profile:</span> ${match.missing_skills.map(h).join(', ')}</div>`;
        }
        if (match.tips?.length) {
            html += `<div class="match-tips">${match.tips.slice(0, 2).map(t => '<span>&rarr; ' + h(t) + '</span>').join('')}</div>`;
        }
        html += '</div>';
    }

    /* Big CTA: Copy All Connection Messages */
    html += `<div class="sum-cta">
        <button class="btn-copy-all" onclick="copyAllConnections(this)">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            Copy All Connection Messages
        </button>
    </div>`;

    Q('section-summary').innerHTML = html;
    show('section-summary');
}

/* Copy all first-variant connection requests as a list */
function copyAllConnections(btn) {
    try {
        const lines = allPeople.map(p => {
            const msgs = p.personalized_messages || {};
            const conn = (msgs.connection_requests || [])[0];
            if (!conn) return null;
            return `--- ${p.name} (${p.job_title || p.category}) ---\n${conn.text}`;
        }).filter(Boolean);

        if (!lines.length) { toast('No connection messages to copy'); return; }
        const text = lines.join('\n\n');
        copyText(btn, text);
        /* Auto-log: copied all connection messages */
        fetch('/api/activity', {method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({action_type: 'messaged', company: currentJob.company || '', details: 'Copied all connection messages'})
        }).catch(() => {});
    } catch (e) {
        console.error(e);
        toast('Could not copy messages');
    }
}

/* ======================================================================
   Person Card — compact row, accordion expand, LinkedIn-first
   ====================================================================== */

function addPersonCard(person) {
    try {
        const msgs = person.personalized_messages || {};
        const conns = msgs.connection_requests || [];
        const fus = msgs.followups || [];
        const emails = person.emails || [];
        const id = cid++;

        const icons = { recruiter: '🎯', hiring_manager: '👤', leadership: '⭐', hr: '🤝', team_member: '💼' };
        const labels = { recruiter: 'Recruiter', hiring_manager: 'Hiring Manager', leadership: 'Leadership', hr: 'HR', team_member: 'Team' };
        const sty = { professional: 'Pro', friendly: 'Friendly', direct: 'Bold', formal: 'Pro', conversational: 'Friendly', value_focused: 'Bold', warm: 'Friendly' };

        /* First connection request text for quick copy */
        const quickMsg = conns[0]?.text || '';

        const card = document.createElement('div');
        card.className = 'person-card';
        card.dataset.id = id;

        /* ---- Compact row (always visible) ---- */
        card.innerHTML = `
            <div class="pc-compact" onclick="toggleCard(${id})">
                <div class="pc-left">
                    <span class="pc-icon">${icons[person.category] || '👤'}</span>
                    <div class="pc-info">
                        <div class="pc-name-row">
                            <span class="pc-name">${h(person.name)}</span>
                            <span class="category-badge ${h(person.category)}">${h(labels[person.category] || person.category)}</span>
                        </div>
                        ${person.job_title ? `<div class="pc-title">${h(person.job_title)}</div>` : ''}
                    </div>
                </div>
                <div class="pc-right" onclick="event.stopPropagation()">
                    ${quickMsg ? `<button class="quick-copy" onclick="copyText(this, ${A(quickMsg)})" title="Copy connection message">Copy</button>` : ''}
                    ${person.profile_url ? `<a href="${h(person.profile_url)}" target="_blank" class="btn-linkedin" title="Open LinkedIn profile">LinkedIn</a>` : ''}
                </div>
            </div>

            <!-- Expanded detail (hidden by default) -->
            <div class="pc-detail hidden" id="detail-${id}">
                ${emails.length ? `
                    <div class="pc-emails">
                        <span class="pc-emails-label">Email:</span>
                        ${emails.slice(0, 3).map((e, i) =>
                            `<span class="email-chip ${i === 0 ? 'primary' : ''}" onclick="event.stopPropagation();copyText(this,${A(e)})" title="Click to copy">${h(e)}</span>`
                        ).join('')}
                    </div>
                ` : ''}

                ${person.why ? `<div class="pc-why-detail"><strong>Why contact:</strong> ${h(person.why)}</div>` : ''}

                <div class="pc-msgs">
                    ${renderMsgBlock('Connection Request', conns, 'c' + id, sty)}
                    ${renderMsgBlock('Follow-up', fus, 'f' + id, sty)}
                </div>
            </div>
        `;

        Q('people-list').appendChild(card);
    } catch (e) {
        console.error('addPersonCard error:', e);
    }
}

/* Render a message block with variant tabs (Pro / Friendly / Bold) */
function renderMsgBlock(label, items, group, sty) {
    if (!items || !items.length) return '';

    const tabs = items.length > 1
        ? `<div class="vtabs">${items.map((it, i) =>
            `<button class="vtab ${i === 0 ? 'active' : ''}" onclick="event.stopPropagation();switchV(this,'${group}',${i})">${h(sty[it.style] || it.style || 'Variant ' + (i + 1))}</button>`
          ).join('')}</div>`
        : '';

    const panels = items.map((it, i) => {
        const text = it.text || it.body || '';
        return `<div class="vpanel ${i ? 'hidden' : ''}" data-group="${group}" data-idx="${i}">
            <div class="msg-text">${h(text)}</div>
            <div class="msg-actions">
                ${it.char_count ? `<span class="char-count ${it.char_count <= 300 ? 'ok' : 'warn'}">${it.char_count}/300</span>` : '<span></span>'}
                <button class="btn-copy-sm" onclick="event.stopPropagation();copyText(this,${A(text)})">Copy</button>
            </div>
        </div>`;
    }).join('');

    return `<div class="msg-block">
        <div class="msg-label">${label} ${tabs}</div>
        ${panels}
    </div>`;
}

/* ---- Accordion: only one card open at a time ---- */
function toggleCard(id) {
    try {
        const detail = Q(`detail-${id}`);
        const card = detail?.parentElement;
        if (!detail || !card) return;

        const wasOpen = !detail.classList.contains('hidden');

        /* Close previously open card */
        if (expandedCard !== null && expandedCard !== id) {
            const prev = Q(`detail-${expandedCard}`);
            if (prev) {
                prev.classList.add('hidden');
                prev.parentElement.classList.remove('expanded');
            }
        }

        if (wasOpen) {
            detail.classList.add('hidden');
            card.classList.remove('expanded');
            expandedCard = null;
        } else {
            detail.classList.remove('hidden');
            card.classList.add('expanded');
            expandedCard = id;
            setTimeout(() => card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
        }
    } catch (e) { console.error('toggleCard error:', e); }
}

/* Switch variant tab */
function switchV(btn, group, idx) {
    try {
        btn.parentElement.querySelectorAll('.vtab').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll(`.vpanel[data-group="${group}"]`).forEach(p =>
            p.classList.toggle('hidden', parseInt(p.dataset.idx) !== idx)
        );
    } catch (e) { console.error('switchV error:', e); }
}

/* ======================================================================
   Render functions (research, salary, patterns, prep, intel, strategy)
   ====================================================================== */

function renderResearch(d) {
    try {
        let s = '';
        [...(d.news || []).slice(0, 3), ...(d.culture || []).slice(0, 2)].forEach(n => {
            s += `<a href="${h(n.url)}" target="_blank" class="research-item">
                <div class="research-title">${h(n.title)}</div>
                <div class="research-snippet">${h(n.snippet)}</div>
            </a>`;
        });
        Q('company-research').innerHTML = s || '<p class="muted">No info found.</p>';
    } catch (e) { console.error('renderResearch:', e); }
}

function renderSalary(d) {
    try {
        let s = '';
        if (d.estimated_range && d.estimated_range !== 'Not found') {
            s += `<div class="salary-range"><span class="salary-amount">${h(d.estimated_range)}</span><span class="muted">estimated</span></div>`;
        }
        (d.sources || []).slice(0, 2).forEach(x => {
            s += `<a href="${h(x.url)}" target="_blank" class="research-item"><div class="research-title">${h(x.title)}</div></a>`;
        });
        Q('salary-data').innerHTML = s || '<p class="muted">No data.</p>';
    } catch (e) { console.error('renderSalary:', e); }
}

function renderPatterns(d) {
    try {
        Q('email-patterns').innerHTML = `
            <div class="patterns-grid">${(d.patterns || []).map(p =>
                `<div class="pattern-item" onclick="copyText(this,${A(p.example)})">
                    <code>${h(p.pattern)}</code><span>${h(p.example)}</span>
                </div>`
            ).join('')}</div>
            ${d.note ? `<div class="email-note">${h(d.note)}</div>` : ''}
        `;
    } catch (e) { console.error('renderPatterns:', e); }
}

function renderPrep(p) {
    try {
        let html = '';
        if (p.key_skills?.length) {
            html += `<div class="prep-section"><h3>Key Skills</h3>
                <div class="skills-cloud">
                    ${p.key_skills.map(s => `<span class="skill-tag">${h(s)}</span>`).join('')}
                    ${(p.soft_skills || []).map(s => `<span class="skill-tag soft">${h(s)}</span>`).join('')}
                </div>
            </div>`;
        }
        if (p.tech_questions?.length) {
            html += `<div class="prep-section"><h3>Questions They'll Ask</h3>
                <ol class="prep-list">${p.tech_questions.map(q => `<li>${h(q)}</li>`).join('')}</ol>
            </div>`;
        }
        if (p.behavioral_questions?.length) {
            html += `<div class="prep-section"><h3>Behavioral</h3>
                <ol class="prep-list">${p.behavioral_questions.map(q => `<li>${h(q)}</li>`).join('')}</ol>
            </div>`;
        }
        if (p.questions_to_ask?.length) {
            html += `<div class="prep-section"><h3>Ask Them</h3>
                <ol class="prep-list">${p.questions_to_ask.map(q => `<li>${h(q)}</li>`).join('')}</ol>
            </div>`;
        }
        Q('interview-prep').innerHTML = html;
    } catch (e) { console.error('renderPrep:', e); }
}

function renderIntel(d) {
    try {
        let s = '';
        if (d.process) s += `<div class="prep-section"><h3>Process</h3><p style="font-size:0.8rem">${h(d.process)}</p></div>`;
        if (d.questions?.length) s += `<div class="prep-section"><h3>Real Questions</h3><ol class="prep-list">${d.questions.map(q => `<li>${h(q)}</li>`).join('')}</ol></div>`;
        if (d.tips?.length) s += `<div class="prep-section"><h3>Tips</h3><ul class="prep-list">${d.tips.map(t => `<li>${h(t)}</li>`).join('')}</ul></div>`;
        Q('interview-intel').innerHTML = s;
    } catch (e) { console.error('renderIntel:', e); }
}

function renderStrategy(d) {
    try {
        let s = '';
        if (d.priority_order?.length) {
            s += '<h3 style="font-size:0.78rem;color:var(--purple);margin-bottom:6px">Contact Order</h3><div class="strategy-list">';
            d.priority_order.slice(0, 5).forEach((p, i) => {
                s += `<div class="strategy-item"><span class="priority-num">${i + 1}</span><div><strong style="font-size:0.82rem">${h(p.name)}</strong><p class="muted" style="font-size:0.72rem">${h(p.reason)}</p></div></div>`;
            });
            s += '</div>';
        }
        if (d.two_week_plan?.length) {
            s += '<h3 style="font-size:0.78rem;color:var(--purple);margin:10px 0 6px">2-Week Plan</h3><div class="plan-timeline">';
            d.two_week_plan.slice(0, 8).forEach(x => {
                s += `<div class="plan-day"><span class="plan-day-num">Day ${x.day}</span><p style="font-size:0.78rem">${h(x.action)}</p></div>`;
            });
            s += '</div>';
        }
        Q('networking-strategy').innerHTML = s || '<p class="muted">Not available.</p>';
    } catch (e) { console.error('renderStrategy:', e); }
}

/* ======================================================================
   Downloads
   ====================================================================== */

function downloadCSV() {
    try {
        if (!allPeople.length) return;
        const co = currentJob.company || 'contacts';
        let csv = 'Name,Title,Category,LinkedIn,Email,Connection Message\n';
        allPeople.forEach(p => {
            const cr = ((p.personalized_messages || {}).connection_requests || [{}])[0];
            csv += `"${ce(p.name)}","${ce(p.job_title)}","${ce(p.category)}","${ce(p.profile_url)}","${ce((p.emails || [])[0] || '')}","${ce(cr.text || '')}"\n`;
        });
        dl(new Blob([csv], { type: 'text/csv' }), `${co.replace(/\s+/g, '_')}_contacts.csv`);
    } catch (e) { console.error('downloadCSV:', e); toast('Download failed'); }
}

function downloadPDF() {
    if (currentJobId) window.open(`/export/report/${currentJobId}`, '_blank');
}

function downloadCoverPDF() {
    if (currentJobId) window.open(`/export/cover-letter/${currentJobId}`, '_blank');
}

function dl(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
}

/* ======================================================================
   History
   ====================================================================== */

function saveHistory(d) {
    try {
        const hist = JSON.parse(localStorage.getItem('celina_history') || '[]');
        hist.unshift({
            input: Q('smart-input').value.trim(),
            title: d.title || '',
            company: d.company || '',
            people: d.total_people || 0,
            date: new Date().toLocaleDateString(),
        });
        if (hist.length > 15) hist.pop();
        localStorage.setItem('celina_history', JSON.stringify(hist));
        renderHistory();
    } catch (e) { console.error('saveHistory:', e); }
}

function renderHistory() {
    try {
        const hist = JSON.parse(localStorage.getItem('celina_history') || '[]');
        const el = Q('history-list');
        if (!el) return;
        if (!hist.length) { el.innerHTML = '<p class="muted">No searches yet.</p>'; return; }
        el.innerHTML = hist.slice(0, 6).map(x => `
            <div class="history-item" onclick="runFromHistory(${A(x.input)})">
                <div class="history-main">
                    <strong>${h(x.title || x.company || x.input)}</strong>
                    ${x.company && x.title ? ` <span class="muted">at ${h(x.company)}</span>` : ''}
                </div>
                <div class="history-meta"><span>${x.people} people</span><span>${h(x.date)}</span></div>
            </div>
        `).join('');
    } catch (e) { console.error('renderHistory:', e); }
}

function runFromHistory(input) {
    try {
        const el = Q('smart-input');
        if (el) { el.value = input; go(); }
    } catch (e) { console.error('runFromHistory:', e); }
}

/* ======================================================================
   Profile check
   ====================================================================== */

async function checkProfile() {
    try {
        const r = await fetch('/profile/check');
        const d = await r.json();
        if (!d.has_profile) show('profile-prompt');
    } catch (_) {}
}

/* ======================================================================
   UI Helpers
   ====================================================================== */

function resetUI() {
    allPeople = [];
    currentJob = {};
    currentJobId = '';
    cid = 0;
    expandedCard = null;
    progressPct = 0;
    const list = Q('people-list');
    if (list) list.innerHTML = '';
    ['section-summary', 'section-actions', 'section-people', 'section-intel',
     'section-cover', 'section-email-patterns', 'section-interview-all', 'section-strategy'
    ].forEach(id => {
        const el = Q(id);
        if (el) el.classList.add('hidden');
    });
}

function setLoading(on) {
    try {
        const btn = Q('go-btn');
        if (btn) btn.disabled = on;
        const txt = Q('go-text');
        if (txt) txt.textContent = on ? '' : 'Go';
        const spin = Q('go-spinner');
        if (spin) spin.classList.toggle('hidden', !on);
        if (on) {
            show('progress');
            Q('progress-fill').style.width = '0%';
            Q('progress-text').textContent = 'Starting...';
        }
    } catch (e) { console.error('setLoading:', e); }
}

function show(id) { const el = Q(id); if (el) el.classList.remove('hidden'); }
function showEl(id) { const el = Q(id); if (el) el.style.display = ''; }

function toggleJD() {
    try { Q('jd-content').classList.toggle('hidden'); } catch (_) {}
}

function toggleEl(id) {
    try {
        const el = Q(id);
        if (!el) return;
        el.classList.toggle('hidden');
        const icon = Q(id + '-icon');
        if (icon) icon.textContent = el.classList.contains('hidden') ? '+' : '\u2212';
    } catch (_) {}
}

function Q(id) { return document.getElementById(id); }

/* ======================================================================
   Copy to clipboard
   ====================================================================== */

function copyText(btn, text) {
    try {
        navigator.clipboard.writeText(text).then(() => {
            markCopied(btn);
        }).catch(() => {
            /* Fallback for older browsers */
            const t = document.createElement('textarea');
            t.value = text;
            t.style.position = 'fixed';
            t.style.left = '-9999px';
            document.body.appendChild(t);
            t.select();
            document.execCommand('copy');
            document.body.removeChild(t);
            markCopied(btn);
        });
    } catch (e) { console.error('copyText:', e); }
}

function markCopied(btn) {
    if (!btn) return;
    const orig = btn.textContent;
    btn.classList.add('copied');
    if (btn.tagName === 'BUTTON') btn.textContent = 'Copied!';
    setTimeout(() => {
        btn.classList.remove('copied');
        if (btn.tagName === 'BUTTON') btn.textContent = orig;
    }, 1200);
    /* Auto-log: message copied */
    fetch('/api/activity', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action_type: 'messaged', company: currentJob.company || '', details: 'Copied a message'})
    }).catch(() => {});
}

/* ======================================================================
   Toast notifications
   ====================================================================== */

function toast(msg) {
    try {
        document.querySelectorAll('.toast').forEach(t => t.remove());
        const t = document.createElement('div');
        t.className = 'toast error';
        t.textContent = msg;
        document.body.appendChild(t);
        requestAnimationFrame(() => t.classList.add('show'));
        setTimeout(() => {
            t.classList.remove('show');
            setTimeout(() => t.remove(), 300);
        }, 4000);
    } catch (_) {}
}

/* Backwards compat alias */
function showToast(m) { toast(m); }

/* ======================================================================
   Utils
   ====================================================================== */

function h(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function J(s) { return JSON.stringify(s || ''); }
/* JSON string escaped for safe embedding inside double-quoted HTML attributes */
function A(s) { return J(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;'); }
function ce(s) { return (s || '').replace(/"/g, '""'); }

/* Backwards compat aliases */
function esc(s) { return h(s); }
function escJ(s) { return J(s); }
