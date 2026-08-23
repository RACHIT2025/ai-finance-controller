// FinController Frontend Application Logic

let activeFilter = 'ALL';
let currentReport = null;
let allTableRows = [];

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initEventListeners();
  fetchInitialData();
  startTelemetryPolling();
});

// 1. TAB NAVIGATION
function initTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      document.getElementById(targetId).classList.add('active');

      if (targetId === 'tab-audit') {
        loadAuditChain();
      } else if (targetId === 'tab-qa') {
        loadSummary();
      }
    });
  });
}

// 2. EVENT LISTENERS
function initEventListeners() {
  document.getElementById('btnRunReconcile').addEventListener('click', runReconciliation);
  document.getElementById('btnVerifyChain').addEventListener('click', verifyAuditChain);
  document.getElementById('btnSendChat').addEventListener('click', sendChatMessage);
  document.getElementById('chatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatMessage();
  });

  // Table filter chips
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.getAttribute('data-filter');
      renderTable();
    });
  });

  // Table search
  document.getElementById('tableSearchInput').addEventListener('input', renderTable);

  // Quick prompt chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const query = chip.getAttribute('data-query');
      document.getElementById('chatInput').value = query;
      sendChatMessage();
    });
  });

  // Fault simulations
  document.getElementById('btnSimulateTimeout').addEventListener('click', () => simulateFault('upstream_timeout'));
  document.getElementById('btnSimulateLLMOutage').addEventListener('click', () => simulateFault('llm_offline'));
  document.getElementById('btnSimulateTamper').addEventListener('click', () => simulateFault('audit_tamper'));
  document.getElementById('btnClearTelemetry').addEventListener('click', async () => {
    try {
      await fetch('/api/telemetry/clear', { method: 'POST' });
      document.getElementById('telemetryLogBody').innerHTML = `
        <div class="log-entry" style="color: var(--text-muted); font-style: italic; opacity: 0.7;">
          [Telemetry buffer cleared. New resilience & recovery events will stream here.]
        </div>
      `;
    } catch (err) {
      document.getElementById('telemetryLogBody').innerHTML = '';
    }
  });
}

// 3. RECONCILIATION RUNNER
async function runReconciliation() {
  const btn = document.getElementById('btnRunReconcile');
  btn.disabled = true;
  btn.innerHTML = 'Reconciling...';

  try {
    const res = await fetch('/api/reconcile/benchmark', { method: 'POST' });
    const data = await res.json();
    currentReport = data;
    updateKPIs(data.summary, data.audit_block_count, data.audit_chain_head);
    processTableData(data);
    renderTable();
    loadAuditChain();
    loadSummary();
  } catch (err) {
    console.error('Reconciliation error:', err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
      Run Reconciliation
    `;
  }
}

// 4. KPI STATS UPDATE
function updateKPIs(s, auditCount, chainHead) {
  if (!s) return;
  document.getElementById('kpiReconciledVol').innerText = `₹${s.reconciled_volume.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('kpiTotalVol').innerText = `Gateway: ₹${s.total_gateway_volume.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('kpiAutoRate').innerText = `${s.auto_match_rate.toFixed(1)}%`;
  document.getElementById('kpiMatchedPairs').innerText = `${s.auto_matched_count} high-confidence pairs`;
  document.getElementById('kpiHumanReview').innerText = `${s.human_review_count}`;
  document.getElementById('kpiFeesVol').innerText = `₹${s.total_fee_volume.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('kpiAuditBlocks').innerText = `${auditCount || 0}`;
  document.getElementById('kpiChainHead').innerText = chainHead ? `Head: ${chainHead.substring(0, 10)}...` : 'Genesis sealed';

  // Counts on filter chips
  document.getElementById('cntAuto').innerText = `${s.auto_matched_count}`;
  document.getElementById('cntReview').innerText = `${s.human_review_count}`;
  document.getElementById('cntUnmatchedGw').innerText = `${s.unmatched_gateway_count}`;
  document.getElementById('cntUnmatchedBnk').innerText = `${s.unmatched_bank_count}`;
}

// 5. PROCESS & RENDER TABLE
function processTableData(report) {
  allTableRows = [];

  // Auto Matches
  report.matches.forEach(m => {
    allTableRows.push({
      category: 'AUTO_MATCHED',
      id: m.match_id,
      reason: m.reason_code,
      gw_refs: m.gateway_tx_ids.join(', '),
      bnk_refs: m.bank_tx_ids.join(', '),
      discrepancy: `₹${m.amount_discrepancy.toFixed(2)}`,
      confidence: m.confidence,
      explanation: m.explanation,
    });
  });

  // Human Reviews
  report.human_reviews.forEach(hr => {
    allTableRows.push({
      category: 'NEEDS_HUMAN_REVIEW',
      id: hr.match_id,
      reason: hr.reason_code,
      gw_refs: hr.gateway_tx_ids.join(', '),
      bnk_refs: hr.bank_tx_ids.join(', '),
      discrepancy: `₹${hr.amount_discrepancy.toFixed(2)}`,
      confidence: hr.confidence,
      explanation: hr.explanation,
    });
  });

  // Unmatched Gateway
  report.unmatched_gateway.forEach(gw => {
    allTableRows.push({
      category: 'UNMATCHED_GW',
      id: gw.id,
      reason: gw.metadata?.unmatched_reason || 'UNSETTLED_GATEWAY_PAYMENT',
      gw_refs: gw.reference_id,
      bnk_refs: 'None',
      discrepancy: `₹${gw.net_amount.toFixed(2)}`,
      confidence: 0.0,
      explanation: `Gateway payment of ₹${gw.amount.toFixed(2)} has no corresponding bank settlement.`,
    });
  });

  // Unmatched Bank
  report.unmatched_bank.forEach(bnk => {
    allTableRows.push({
      category: 'UNMATCHED_BNK',
      id: bnk.id,
      reason: bnk.metadata?.unmatched_reason || 'ORPHANED_BANK_CREDIT',
      gw_refs: 'None',
      bnk_refs: bnk.reference_id,
      discrepancy: `₹${bnk.net_amount.toFixed(2)}`,
      confidence: 0.0,
      explanation: `Direct bank deposit of ₹${bnk.net_amount.toFixed(2)} has no gateway source entry.`,
    });
  });
}

function renderTable() {
  const tbody = document.getElementById('reconTableBody');
  const searchVal = document.getElementById('tableSearchInput').value.toLowerCase().trim();

  let filtered = allTableRows.filter(row => {
    if (activeFilter !== 'ALL' && row.category !== activeFilter) return false;
    if (searchVal) {
      const matchStr = `${row.id} ${row.reason} ${row.gw_refs} ${row.bnk_refs} ${row.discrepancy}`.toLowerCase();
      return matchStr.includes(searchVal);
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center empty-state">No matching reconciliation records found.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(r => {
    let catBadge = '';
    if (r.category === 'AUTO_MATCHED') catBadge = `<span class="category-tag cat-auto">Auto Matched</span>`;
    else if (r.category === 'NEEDS_HUMAN_REVIEW') catBadge = `<span class="category-tag cat-review">Human Review</span>`;
    else catBadge = `<span class="category-tag cat-unmatched">Unmatched</span>`;

    const confPct = Math.round(r.confidence * 100);

    return `
      <tr>
        <td>${catBadge}</td>
        <td><span class="code-font">${r.id}</span></td>
        <td><span class="code-font">${r.reason}</span></td>
        <td><span class="code-font">${r.gw_refs}</span></td>
        <td><span class="code-font">${r.bnk_refs}</span></td>
        <td>${r.discrepancy}</td>
        <td>
          <div class="confidence-bar">
            <div class="progress-bar-bg"><div class="progress-bar-fill" style="width: ${confPct}%"></div></div>
            <span>${confPct}%</span>
          </div>
        </td>
        <td>
          <button class="btn-sm" onclick="askAboutRecord('${r.id}')">Ask AI</button>
        </td>
      </tr>
    `;
  }).join('');
}

window.askAboutRecord = function(recordId) {
  document.querySelector('.tab-btn[data-tab="tab-qa"]').click();
  document.getElementById('chatInput').value = `Why did record ${recordId} reconcile or fail?`;
  sendChatMessage();
};

// 6. AI Q&A CHAT
async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const query = input.value.trim();
  if (!query) return;

  input.value = '';
  appendChatMessage('user', query);

  const botMsgElem = appendChatMessage('bot', 'Investigating deterministic reconciliation outputs...');

  try {
    const res = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    botMsgElem.querySelector('.message-body').innerHTML = renderMarkdown(data.answer);
    document.getElementById('chatMessages').scrollTop = document.getElementById('chatMessages').scrollHeight;
  } catch (err) {
    botMsgElem.querySelector('.message-body').innerHTML = `<p class="text-danger">Failed to connect to agent: ${err.message}</p>`;
    document.getElementById('chatMessages').scrollTop = document.getElementById('chatMessages').scrollHeight;
  }
}

function appendChatMessage(role, text) {
  const container = document.getElementById('chatMessages');
  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-message ${role}`;
  msgDiv.innerHTML = `
    <div class="message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
    <div class="message-body">${role === 'user' ? `<p>${text}</p>` : renderMarkdown(text)}</div>
  `;
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  return msgDiv;
}

function renderMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`(.*?)`/gim, '<code class="code-font">$1</code>')
    .replace(/\n\n/gim, '<br><br>')
    .replace(/\n/gim, '<br>');
}

// 7. AUDIT CHAIN EXPLORER
async function loadAuditChain() {
  try {
    const res = await fetch('/api/audit/chain');
    const data = await res.json();
    const timeline = document.getElementById('auditChainTimeline');

    if (!data.chain || data.chain.length === 0) {
      timeline.innerHTML = '<p class="text-muted">No audit blocks recorded yet.</p>';
      return;
    }

    timeline.innerHTML = data.chain.slice(-8).reverse().map(b => `
      <div class="audit-block-card">
        <div class="block-header">
          <div>
            <span class="block-index">Block #${b.index}</span>
            <span class="block-type">${b.event_type}</span>
          </div>
          <span class="text-dark code-font">${b.timestamp}</span>
        </div>
        <div class="block-hashes">
          <div><strong>Prev Hash:</strong> <span class="code-font">${b.previous_hash.substring(0, 24)}...</span></div>
          <div><strong>Block Hash:</strong> <span class="code-font">${b.block_hash.substring(0, 24)}...</span></div>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Audit load error:', err);
  }
}

async function verifyAuditChain() {
  const btn = document.getElementById('btnVerifyChain');
  btn.disabled = true;
  btn.innerText = 'Verifying SHA-256 Hashes...';

  try {
    const res = await fetch('/api/audit/verify');
    const data = await res.json();
    const alertBox = document.getElementById('verificationAlert');
    const pill = document.getElementById('auditStatusPill');

    if (data.verified) {
      alertBox.className = 'verification-alert alert-success';
      alertBox.innerHTML = `
        <div class="alert-icon">🛡️</div>
        <div class="alert-content">
          <h4>Tamper-Evident Verification: PASSED</h4>
          <p>${data.message} (${data.total_blocks} blocks sealed)</p>
        </div>
      `;
      pill.className = 'audit-status-pill';
      document.getElementById('auditPillText').innerText = 'Audit Chain: Verified (SHA-256)';
    } else {
      alertBox.className = 'verification-alert alert-danger';
      alertBox.innerHTML = `
        <div class="alert-icon">🚨</div>
        <div class="alert-content">
          <h4>Security Alert: TAMPERING DETECTED</h4>
          <p>${data.message} (Corrupted at index ${data.corrupted_block_index})</p>
        </div>
      `;
      pill.className = 'audit-status-pill';
      pill.style.borderColor = 'var(--accent-rose)';
      pill.style.color = 'var(--accent-rose)';
      document.getElementById('auditPillText').innerText = 'Audit Chain: TAMPER DETECTED';
    }
  } catch (err) {
    console.error(err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      Verify Cryptographic Integrity
    `;
  }
}

// 8. SUMMARY LOADER
async function loadSummary() {
  try {
    const res = await fetch('/api/summary');
    const data = await res.json();
    document.getElementById('executiveSummaryContent').innerHTML = renderMarkdown(data.summary_markdown);
  } catch (err) {
    console.error(err);
  }
}

// 9. RESILIENCE FAULT SIMULATION
async function simulateFault(scenario) {
  try {
    await fetch('/api/simulate-failure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario }),
    });
    fetchTelemetry();
  } catch (err) {
    console.error(err);
  }
}

// 10. TELEMETRY POLLING
function startTelemetryPolling() {
  fetchTelemetry();
  setInterval(fetchTelemetry, 2500);
}

async function fetchTelemetry() {
  try {
    const res = await fetch('/api/telemetry');
    const data = await res.json();
    const body = document.getElementById('telemetryLogBody');
    if (!data.events || data.events.length === 0) {
      body.innerHTML = `
        <div class="log-entry" style="color: var(--text-muted); font-style: italic; opacity: 0.7;">
          [No telemetry events in buffer. Run reconciliation or simulate faults above.]
        </div>
      `;
      return;
    }

    body.innerHTML = data.events.map(e => `
      <div class="log-entry">
        <span class="log-ts">[${e.timestamp.substring(11, 19)}]</span>
        <span class="log-lvl-${e.level}">${e.level}</span>
        <span class="log-comp">&lt;${e.component}&gt;</span>
        <span class="log-msg">${e.message}</span>
      </div>
    `).join('');
  } catch (err) {
    // Ignore polling network glitches
  }
}

async function fetchInitialData() {
  await runReconciliation();
}
