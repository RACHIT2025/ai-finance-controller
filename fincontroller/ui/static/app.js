// FinController Frontend Application Logic - Cloud Edition

let activeFilter = 'ALL';
let currentReport = null;
let allTableRows = [];

// Studio state for customer interactive table
let studioGwRows = [];
let studioBnkRows = [];

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initEventListeners();
  initStudioDefaults();
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

function switchToTab(tabId) {
  const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (targetBtn) {
    targetBtn.click();
  }
}

// 2. EVENT LISTENERS
function initEventListeners() {
  document.getElementById('btnRunReconcile').addEventListener('click', runReconciliation);
  document.getElementById('btnVerifyChain').addEventListener('click', verifyAuditChain);
  document.getElementById('btnSendChat').addEventListener('click', sendChatMessage);
  document.getElementById('chatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatMessage();
  });

  // Header "Enter Your Data" button
  const btnOpenManualStudio = document.getElementById('btnOpenManualStudio');
  if (btnOpenManualStudio) {
    btnOpenManualStudio.addEventListener('click', () => {
      switchToTab('tab-studio');
    });
  }

  // Export buttons
  const btnExportCsv = document.getElementById('btnExportCsv');
  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', exportReconciliationCsv);
  }
  const btnExportCert = document.getElementById('btnExportCert');
  if (btnExportCert) {
    btnExportCert.addEventListener('click', exportAuditCertificate);
  }

  // Studio Interactive Buttons
  const btnAddGwRow = document.getElementById('btnAddGwRow');
  if (btnAddGwRow) {
    btnAddGwRow.addEventListener('click', () => {
      addStudioGwRow(`pay_live_${Date.now().toString().slice(-4)}`, 1000.0, 23.6, `cust_ref_${Date.now().toString().slice(-3)}`, 'captured');
    });
  }
  const btnAddBnkRow = document.getElementById('btnAddBnkRow');
  if (btnAddBnkRow) {
    btnAddBnkRow.addEventListener('click', () => {
      addStudioBnkRow(`UTR_LIVE_${Date.now().toString().slice(-4)}`, 976.4, `SETTL_RZP_BATCH`);
    });
  }
  const btnReconcileStudio = document.getElementById('btnReconcileStudio');
  if (btnReconcileStudio) {
    btnReconcileStudio.addEventListener('click', handleStudioReconciliation);
  }

  // Preset Buttons
  document.querySelectorAll('.btn-preset').forEach(btn => {
    btn.addEventListener('click', () => {
      const preset = btn.getAttribute('data-preset');
      loadStudioPreset(preset);
    });
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

  // Dynamic file upload modal handlers
  const modalUpload = document.getElementById('modalUpload');
  const btnOpenUpload = document.getElementById('btnOpenUploadModal');
  const btnCloseUpload = document.getElementById('btnCloseUploadModal');
  const btnCancelUpload = document.getElementById('btnCancelUpload');
  const formUpload = document.getElementById('formUploadReconcile');

  if (btnOpenUpload) {
    btnOpenUpload.addEventListener('click', () => {
      modalUpload.classList.remove('hidden');
      document.getElementById('uploadStatusMsg').classList.add('hidden');
    });
  }
  if (btnCloseUpload) {
    btnCloseUpload.addEventListener('click', () => modalUpload.classList.add('hidden'));
  }
  if (btnCancelUpload) {
    btnCancelUpload.addEventListener('click', () => modalUpload.classList.add('hidden'));
  }
  if (formUpload) {
    formUpload.addEventListener('submit', handleCustomFileUpload);
  }
}

// 3. CUSTOMER DATA STUDIO (INTERACTIVE SANDBOX)
function initStudioDefaults() {
  loadStudioPreset('saas');
}

function loadStudioPreset(preset) {
  studioGwRows = [];
  studioBnkRows = [];

  if (preset === 'saas') {
    // 1-to-1 with Standard MDR (2% + 18% GST = 2.36%)
    studioGwRows = [
      { id: 'pay_sub_01', amount: 5000.0, fee: 118.0, ref: 'INV_SUB_101', status: 'captured' },
      { id: 'pay_sub_02', amount: 12500.0, fee: 295.0, ref: 'INV_SUB_102', status: 'captured' },
      { id: 'pay_sub_03', amount: 3200.0, fee: 75.52, ref: 'INV_SUB_103', status: 'captured' },
    ];
    studioBnkRows = [
      { id: 'UTR_HDFC_0981', amount: 4882.0, ref: 'INV_SUB_101' },
      { id: 'UTR_HDFC_0982', amount: 12205.0, ref: 'INV_SUB_102' },
      { id: 'UTR_HDFC_0983', amount: 3124.48, ref: 'INV_SUB_103' },
    ];
  } else if (preset === 'split') {
    // 1 Bank batch settling 3 gateway transactions (e-commerce payout)
    studioGwRows = [
      { id: 'pay_cart_item_A', amount: 4500.0, fee: 0.0, ref: 'BATCH_GRP_400', status: 'captured' },
      { id: 'pay_cart_item_B', amount: 3500.0, fee: 0.0, ref: 'BATCH_GRP_400', status: 'captured' },
      { id: 'pay_cart_item_C', amount: 2000.0, fee: 0.0, ref: 'BATCH_GRP_400', status: 'captured' },
      { id: 'pay_unsettled_D', amount: 1800.0, fee: 0.0, ref: 'ESCROW_HOLD', status: 'captured' },
    ];
    studioBnkRows = [
      { id: 'UTR_ICICI_BATCH_400', amount: 10000.0, ref: 'BATCH_GRP_400 (Items A+B+C)' },
      { id: 'UTR_DIRECT_DEPOSIT_99', amount: 750.0, ref: 'DIRECT_OFFLINE_TRANSFER' },
    ];
  } else if (preset === 'ambiguous') {
    // 2 duplicate transactions with same amount -> Engine honestly flags for human review
    studioGwRows = [
      { id: 'pay_AMBIG_DUP_1', amount: 999.0, fee: 0.0, ref: 'REF_CONFLICT_99', status: 'captured' },
      { id: 'pay_AMBIG_DUP_2', amount: 999.0, fee: 0.0, ref: 'REF_CONFLICT_99', status: 'captured' },
    ];
    studioBnkRows = [
      { id: 'UTR_SBI_SINGLE_999', amount: 999.0, ref: 'REF_CONFLICT_99' },
    ];
  } else if (preset === 'clear') {
    studioGwRows = [];
    studioBnkRows = [];
  }

  renderStudioTables();
}

function addStudioGwRow(id, amount, fee, ref, status) {
  studioGwRows.push({ id, amount, fee, ref, status });
  renderStudioTables();
}

function addStudioBnkRow(id, amount, ref) {
  studioBnkRows.push({ id, amount, ref });
  renderStudioTables();
}

function removeStudioGwRow(idx) {
  studioGwRows.splice(idx, 1);
  renderStudioTables();
}

function removeStudioBnkRow(idx) {
  studioBnkRows.splice(idx, 1);
  renderStudioTables();
}

function renderStudioTables() {
  const bodyGw = document.getElementById('bodyGwStudio');
  const bodyBnk = document.getElementById('bodyBnkStudio');
  if (!bodyGw || !bodyBnk) return;

  if (studioGwRows.length === 0) {
    bodyGw.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding: 16px;">No gateway transactions. Click "+ Add Gateway Tx" or choose a preset.</td></tr>`;
  } else {
    bodyGw.innerHTML = studioGwRows.map((r, i) => `
      <tr>
        <td><input type="text" class="studio-input" value="${r.id}" onchange="studioGwRows[${i}].id = this.value"></td>
        <td><input type="number" step="0.01" class="studio-input text-right" value="${r.amount}" onchange="studioGwRows[${i}].amount = parseFloat(this.value) || 0; updateStudioTotals();"></td>
        <td><input type="number" step="0.01" class="studio-input text-right" value="${r.fee}" onchange="studioGwRows[${i}].fee = parseFloat(this.value) || 0; updateStudioTotals();"></td>
        <td><input type="text" class="studio-input" value="${r.ref}" onchange="studioGwRows[${i}].ref = this.value"></td>
        <td>
          <select class="studio-select" onchange="studioGwRows[${i}].status = this.value">
            <option value="captured" ${r.status === 'captured' ? 'selected' : ''}>captured</option>
            <option value="failed" ${r.status === 'failed' ? 'selected' : ''}>failed</option>
            <option value="refunded" ${r.status === 'refunded' ? 'selected' : ''}>refunded</option>
          </select>
        </td>
        <td class="text-center">
          <button class="btn-icon-del" onclick="removeStudioGwRow(${i})" title="Delete row">&times;</button>
        </td>
      </tr>
    `).join('');
  }

  if (studioBnkRows.length === 0) {
    bodyBnk.innerHTML = `<tr><td colspan="4" class="text-center text-muted" style="padding: 16px;">No bank credit rows. Click "+ Add Bank Credit".</td></tr>`;
  } else {
    bodyBnk.innerHTML = studioBnkRows.map((r, i) => `
      <tr>
        <td><input type="text" class="studio-input" value="${r.id}" onchange="studioBnkRows[${i}].id = this.value"></td>
        <td><input type="number" step="0.01" class="studio-input text-right" value="${r.amount}" onchange="studioBnkRows[${i}].amount = parseFloat(this.value) || 0; updateStudioTotals();"></td>
        <td><input type="text" class="studio-input" value="${r.ref}" onchange="studioBnkRows[${i}].ref = this.value"></td>
        <td class="text-center">
          <button class="btn-icon-del" onclick="removeStudioBnkRow(${i})" title="Delete row">&times;</button>
        </td>
      </tr>
    `).join('');
  }

  updateStudioTotals();
}

function updateStudioTotals() {
  const netGw = studioGwRows.reduce((acc, r) => acc + (parseFloat(r.amount) || 0) - (parseFloat(r.fee) || 0), 0);
  const totalBnk = studioBnkRows.reduce((acc, r) => acc + (parseFloat(r.amount) || 0), 0);
  
  const gwTotalEl = document.getElementById('studioGwTotal');
  const bnkTotalEl = document.getElementById('studioBnkTotal');
  if (gwTotalEl) gwTotalEl.innerText = `₹${netGw.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (bnkTotalEl) bnkTotalEl.innerText = `₹${totalBnk.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

async function handleStudioReconciliation() {
  const btn = document.getElementById('btnReconcileStudio');
  if (!studioGwRows.length || !studioBnkRows.length) {
    alert('Please enter at least 1 gateway transaction and 1 bank credit.');
    return;
  }

  btn.disabled = true;
  btn.innerText = 'Reconciling Live...';

  const payload = {
    gateway_transactions: studioGwRows.map(r => ({
      id: r.id,
      amount: parseFloat(r.amount) || 0.0,
      fee: parseFloat(r.fee) || 0.0,
      reference_id: r.ref || r.id,
      status: r.status || 'captured',
    })),
    bank_transactions: studioBnkRows.map(r => ({
      id: r.id,
      amount: parseFloat(r.amount) || 0.0,
      reference_id: r.ref || r.id,
      description: r.ref || 'Customer Direct Entry',
    })),
    session_title: 'Customer Live Sandbox Session',
  };

  try {
    const res = await fetch('/api/reconcile/manual-entry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Reconciliation failed');
    }

    const data = await res.json();
    currentReport = data;
    updateKPIs(data.summary, data.audit_block_count, data.audit_chain_head);
    processTableData(data);
    renderTable();
    loadAuditChain();
    loadSummary();

    // Switch to reconciliation results tab
    switchToTab('tab-reconciliation');
  } catch (err) {
    alert(`Reconciliation error: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
      Reconcile My Data Live
    `;
  }
}

// 4. EXPORT HANDLERS
function exportReconciliationCsv() {
  window.location.href = '/api/export/csv';
}

function exportAuditCertificate() {
  window.open('/api/export/audit-cert', '_blank');
}

// 5. FILE UPLOAD HANDLER
async function handleCustomFileUpload(e) {
  e.preventDefault();
  const gwFile = document.getElementById('uploadGwFile').files[0];
  const bnkFile = document.getElementById('uploadBnkFile').files[0];
  const gwMapping = document.getElementById('uploadGwMapping').value.trim();
  const bnkMapping = document.getElementById('uploadBnkMapping').value.trim();
  const statusMsg = document.getElementById('uploadStatusMsg');
  const submitBtn = document.getElementById('btnSubmitUpload');

  if (!gwFile || !bnkFile) {
    statusMsg.className = 'upload-status-msg error';
    statusMsg.innerText = 'Please select both a Gateway file and a Bank Statement file.';
    statusMsg.classList.remove('hidden');
    return;
  }

  const formData = new FormData();
  formData.append('gateway_file', gwFile);
  formData.append('bank_file', bnkFile);
  if (gwMapping) formData.append('gateway_mapping', gwMapping);
  if (bnkMapping) formData.append('bank_mapping', bnkMapping);

  submitBtn.disabled = true;
  submitBtn.innerText = 'Reconciling Live Data...';
  statusMsg.classList.add('hidden');

  try {
    const res = await fetch('/api/reconcile/upload', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Ingestion error');
    }
    const data = await res.json();
    currentReport = data;
    updateKPIs(data.summary, data.audit_block_count, data.audit_chain_head);
    processTableData(data);
    renderTable();
    loadAuditChain();
    loadSummary();

    statusMsg.className = 'upload-status-msg success';
    statusMsg.innerText = `Reconciliation Complete! Match Rate: ${data.summary.match_rate ? data.summary.match_rate.toFixed(1) : data.summary.auto_match_rate.toFixed(1)}%.`;
    statusMsg.classList.remove('hidden');

    setTimeout(() => {
      document.getElementById('modalUpload').classList.add('hidden');
      submitBtn.disabled = false;
      submitBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        Reconcile Live Data
      `;
      switchToTab('tab-reconciliation');
    }, 1000);
  } catch (err) {
    statusMsg.className = 'upload-status-msg error';
    statusMsg.innerText = `Error: ${err.message}`;
    statusMsg.classList.remove('hidden');
    submitBtn.disabled = false;
    submitBtn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      Reconcile Live Data
    `;
  }
}

// 6. BENCHMARK RUNNER
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
      Benchmark (50+ Cases)
    `;
  }
}

// 7. KPI STATS UPDATER
function updateKPIs(summary, auditBlocks, chainHead) {
  if (!summary) return;
  document.getElementById('kpiReconciledVol').innerText = `₹${(summary.reconciled_volume || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('kpiTotalVol').innerText = `Processed ₹${(summary.total_gateway_volume || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })} total`;

  const rate = summary.match_rate !== undefined ? summary.match_rate : summary.auto_match_rate;
  document.getElementById('kpiAutoRate').innerText = `${(rate || 0).toFixed(1)}%`;
  document.getElementById('kpiMatchedPairs').innerText = `${summary.auto_matched_count || 0} high-confidence pairs`;

  document.getElementById('kpiHumanReview').innerText = summary.human_review_count || 0;
  document.getElementById('kpiFeesVol').innerText = `₹${(summary.total_fee_volume || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  document.getElementById('kpiAuditBlocks').innerText = auditBlocks || 1;
  document.getElementById('kpiChainHead').innerText = chainHead ? `Hash: ${chainHead.substring(0, 12)}...` : 'Sealed & Valid';
}

// 8. TABLE PROCESSING & RENDERING
function processTableData(report) {
  allTableRows = [];

  let countAuto = 0;
  let countReview = 0;
  let countUnmatchedGw = 0;
  let countUnmatchedBnk = 0;

  // 1. Auto-Matched Records
  if (report.matches) {
    report.matches.forEach(m => {
      countAuto++;
      allTableRows.push({
        category: 'AUTO_MATCHED',
        id: m.match_id,
        reason_code: m.reason_code,
        gw_refs: m.gateway_tx_ids.join(', '),
        bnk_refs: m.bank_tx_ids.join(', '),
        discrepancy: m.amount_discrepancy,
        confidence: m.confidence_score,
        explanation: m.explanation,
        settled_net: m.settled_net_amount,
      });
    });
  }

  // 2. Needs Human Review (Ambiguous / Duplicate Cases)
  if (report.human_reviews) {
    report.human_reviews.forEach(hr => {
      countReview++;
      allTableRows.push({
        category: 'NEEDS_HUMAN_REVIEW',
        id: hr.match_id,
        reason_code: hr.reason_code,
        gw_refs: hr.gateway_tx_ids.join(', '),
        bnk_refs: hr.bank_tx_ids.join(', '),
        discrepancy: hr.amount_discrepancy,
        confidence: hr.confidence_score,
        explanation: hr.explanation,
        settled_net: hr.settled_net_amount,
      });
    });
  }

  // 3. Unmatched Gateway Transactions
  if (report.unmatched_gateway) {
    report.unmatched_gateway.forEach(ug => {
      countUnmatchedGw++;
      const reason = ug.metadata && ug.metadata.unmatched_reason ? ug.metadata.unmatched_reason : 'UNSETTLED_GATEWAY_PAYMENT';
      allTableRows.push({
        category: 'UNMATCHED_GW',
        id: ug.id,
        reason_code: reason,
        gw_refs: ug.id + (ug.reference_id ? ` (${ug.reference_id})` : ''),
        bnk_refs: '—',
        discrepancy: ug.net_amount,
        confidence: 0.0,
        explanation: `Gross ₹${ug.amount.toFixed(2)}, fee ₹${ug.fee.toFixed(2)}, status '${ug.status}'. No matching bank deposit in clearing window (pending clearing / escrow).`,
        settled_net: ug.net_amount,
      });
    });
  }

  // 4. Unmatched Bank Credits
  if (report.unmatched_bank) {
    report.unmatched_bank.forEach(ub => {
      countUnmatchedBnk++;
      const reason = ub.metadata && ub.metadata.unmatched_reason ? ub.metadata.unmatched_reason : 'ORPHANED_BANK_CREDIT';
      allTableRows.push({
        category: 'UNMATCHED_BNK',
        id: ub.id,
        reason_code: reason,
        gw_refs: '—',
        bnk_refs: ub.id + (ub.reference_id ? ` (${ub.reference_id})` : ''),
        discrepancy: ub.net_amount,
        confidence: 0.0,
        explanation: `Narration: ${ub.description || 'Direct Credit'}. Direct bank deposit without matching gateway settlement.`,
        settled_net: ub.net_amount,
      });
    });
  }

  // Update counts
  document.getElementById('cntAuto').innerText = countAuto;
  document.getElementById('cntReview').innerText = countReview;
  document.getElementById('cntUnmatchedGw').innerText = countUnmatchedGw;
  document.getElementById('cntUnmatchedBnk').innerText = countUnmatchedBnk;
}

function renderTable() {
  const tbody = document.getElementById('reconTableBody');
  const query = document.getElementById('tableSearchInput').value.toLowerCase().trim();

  const filtered = allTableRows.filter(row => {
    if (activeFilter !== 'ALL' && row.category !== activeFilter) return false;
    if (query) {
      const matchSearch =
        row.id.toLowerCase().includes(query) ||
        row.reason_code.toLowerCase().includes(query) ||
        row.gw_refs.toLowerCase().includes(query) ||
        row.bnk_refs.toLowerCase().includes(query) ||
        row.explanation.toLowerCase().includes(query) ||
        row.settled_net.toString().includes(query);
      if (!matchSearch) return false;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center empty-state">No records match the selected filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(r => {
    let badgeClass = 'badge-success';
    let label = 'Auto-Matched';

    if (r.category === 'NEEDS_HUMAN_REVIEW') {
      badgeClass = 'badge-warning';
      label = 'Needs Review';
    } else if (r.category === 'UNMATCHED_GW') {
      badgeClass = 'badge-danger';
      label = 'Unmatched GW';
    } else if (r.category === 'UNMATCHED_BNK') {
      badgeClass = 'badge-danger';
      label = 'Unmatched BNK';
    }

    const confPct = Math.round(r.confidence * 100);
    let confBarColor = confPct >= 85 ? 'var(--accent-emerald)' : confPct >= 40 ? 'var(--accent-amber)' : 'var(--accent-rose)';

    return `
      <tr>
        <td><span class="badge ${badgeClass}">${label}</span></td>
        <td class="code-font font-bold">${r.id}</td>
        <td><span class="reason-pill">${r.reason_code}</span></td>
        <td class="code-font text-muted-subtle">${r.gw_refs}</td>
        <td class="code-font text-muted-subtle">${r.bnk_refs}</td>
        <td class="amount-cell">₹${Math.abs(r.discrepancy).toFixed(2)}</td>
        <td>
          <div class="conf-wrap">
            <div class="conf-bar-bg"><div class="conf-bar-fill" style="width: ${confPct}%; background-color: ${confBarColor};"></div></div>
            <span class="conf-val">${confPct}%</span>
          </div>
        </td>
        <td>
          <button class="btn-icon" title="Ask AI Copilot to explain" onclick="askAiCopilot('${r.id}')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Explain
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function askAiCopilot(entityId) {
  switchToTab('tab-qa');
  document.getElementById('chatInput').value = `Explain match decision and reason for entity ${entityId}`;
  sendChatMessage();
}

// 9. AI Q&A CHAT
async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const query = input.value.trim();
  if (!query) return;

  const chatContainer = document.getElementById('chatMessages');
  
  // Append User message
  chatContainer.innerHTML += `
    <div class="chat-message user">
      <div class="message-body">
        <p>${escapeHtml(query)}</p>
      </div>
      <div class="message-avatar">👤</div>
    </div>
  `;
  input.value = '';
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Append Thinking state
  const loadingId = `load_${Date.now()}`;
  chatContainer.innerHTML += `
    <div class="chat-message bot" id="${loadingId}">
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <p class="text-muted">Analyzing reconciliation output & audit trail...</p>
      </div>
    </div>
  `;
  chatContainer.scrollTop = chatContainer.scrollHeight;

  try {
    const res = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    const loadEl = document.getElementById(loadingId);
    if (loadEl) {
      loadEl.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-body">
          <div class="message-source-tag">${data.source || 'AI Copilot'}</div>
          <div>${renderMarkdown(data.answer)}</div>
        </div>
      `;
    }
  } catch (err) {
    const loadEl = document.getElementById(loadingId);
    if (loadEl) {
      loadEl.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-body text-danger">
          <p>Error retrieving explanation: ${err.message}</p>
        </div>
      `;
    }
  }
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

// 10. AUDIT TRAIL LOADER & VERIFIER
async function loadAuditChain() {
  try {
    const res = await fetch('/api/audit/chain');
    const data = await res.json();
    const timeline = document.getElementById('auditChainTimeline');
    if (!data.chain || data.chain.length === 0) {
      timeline.innerHTML = '<p class="text-muted">No audit blocks sealed yet.</p>';
      return;
    }

    timeline.innerHTML = data.chain.map(b => `
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

// 11. SUMMARY LOADER
async function loadSummary() {
  try {
    const res = await fetch('/api/summary');
    const data = await res.json();
    document.getElementById('executiveSummaryContent').innerHTML = renderMarkdown(data.summary_markdown);
  } catch (err) {
    console.error(err);
  }
}

// 12. RESILIENCE FAULT SIMULATION
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

// 13. TELEMETRY POLLING
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
    // Ignore polling glitches
  }
}

async function fetchInitialData() {
  await runReconciliation();
}

// Helpers
function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderMarkdown(md) {
  if (!md) return '';
  return md
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/`([^`]+)`/gim, '<code>$1</code>')
    .replace(/\n\n/gim, '<br><br>')
    .replace(/\n/gim, '<br>');
}
