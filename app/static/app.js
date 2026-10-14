/**
 * AI Support Ticket Triage & Git Code Resolver Frontend Logic
 */
document.addEventListener("DOMContentLoaded", () => {
  // State
  let batchResults = [];
  let kbTickets = [];
  let gitApps = [];
  let selectedCsvFile = null;

  // DOM Elements
  const pipelineStatus = document.getElementById("pipeline-status");
  const vectorBadge = document.getElementById("vector-count-badge");
  const toast = document.getElementById("toast");

  // Tabs
  const navTabs = document.querySelectorAll(".nav-tab");
  const tabPanes = document.querySelectorAll(".tab-pane");

  // Single Ticket Form
  const singleForm = document.getElementById("single-ticket-form");
  const ticketNumberInput = document.getElementById("ticket-number");
  const applicationNameInput = document.getElementById("application-name");
  const ticketTitleInput = document.getElementById("ticket-title");
  const ticketDetailsInput = document.getElementById("ticket-details");
  const btnAnalyzeSingle = document.getElementById("btn-analyze-single");
  const btnResetSingle = document.getElementById("btn-reset-single");
  const singleEmptyState = document.getElementById("single-empty-state");
  const singleResultsContainer = document.getElementById("single-results-container");

  // Single Results Elements
  const resTicketId = document.getElementById("res-ticket-id");
  const resAppTag = document.getElementById("res-app-tag");
  const resChannelBadge = document.getElementById("res-channel-badge");
  const resTitle = document.getElementById("res-title");
  const resCategory = document.getElementById("res-category");
  const resCatConf = document.getElementById("res-cat-conf");
  const resPriority = document.getElementById("res-priority");
  const resPriConf = document.getElementById("res-pri-conf");
  const resTopics = document.getElementById("res-topics");

  // Git Code Analysis Elements
  const resGitBox = document.getElementById("res-git-box");
  const gitRepoUrl = document.getElementById("git-repo-url");
  const gitFileLoc = document.getElementById("git-file-loc");
  const gitErrorType = document.getElementById("git-error-type");
  const gitRootCauseText = document.getElementById("git-root-cause-text");
  const gitCodeContext = document.getElementById("git-code-context");
  const gitPatchCode = document.getElementById("git-patch-code");

  // Resolution & Similar Elements
  const resResolution = document.getElementById("res-resolution");
  const resRecConf = document.getElementById("res-rec-conf");
  const resSimilarList = document.getElementById("res-similar-list");
  const resReasoningList = document.getElementById("res-reasoning-list");
  const btnCopyResolution = document.getElementById("btn-copy-resolution");
  const copyToast = document.getElementById("copy-toast");

  // Preset Chips
  const presetChips = document.querySelectorAll(".chip-btn");

  // Batch CSV Elements
  const csvDropzone = document.getElementById("csv-dropzone");
  const csvFileInput = document.getElementById("csv-file-input");
  const fileSelectedBar = document.getElementById("file-selected-bar");
  const selectedFilename = document.getElementById("selected-filename");
  const selectedFilesize = document.getElementById("selected-filesize");
  const btnProcessBatch = document.getElementById("btn-process-batch");
  const btnClearCsv = document.getElementById("btn-clear-csv");
  const btnLoadDemoBatch = document.getElementById("btn-load-demo-batch");
  const batchLoader = document.getElementById("batch-loader");
  const batchResultsWrapper = document.getElementById("batch-results-wrapper");
  const batchMetricTotal = document.getElementById("batch-metric-total");
  const batchMetricConf = document.getElementById("batch-metric-conf");
  const batchMetricGitCount = document.getElementById("batch-metric-git-count");
  const batchMetricCritical = document.getElementById("batch-metric-critical");
  const batchSearchInput = document.getElementById("batch-search-input");
  const batchFilterCat = document.getElementById("batch-filter-cat");
  const batchFilterPriority = document.getElementById("batch-filter-priority");
  const batchTableBody = document.getElementById("batch-table-body");
  const btnExportResultsCsv = document.getElementById("btn-export-results-csv");

  // Git Tab Elements
  const gitReposGrid = document.getElementById("git-repos-grid");

  // Modals
  const detailModal = document.getElementById("detail-modal");
  const modalTicketId = document.getElementById("modal-ticket-id");
  const modalBody = document.getElementById("modal-body");
  const btnCloseModal = document.getElementById("btn-close-modal");

  const ingestModal = document.getElementById("ingest-modal");
  const btnOpenIngestModal = document.getElementById("btn-open-ingest-modal");
  const btnCloseIngestModal = document.getElementById("btn-close-ingest-modal");
  const btnCancelIngest = document.getElementById("btn-cancel-ingest");
  const ingestForm = document.getElementById("ingest-form");

  // KB Elements
  const kbSearchInput = document.getElementById("kb-search-input");
  const kbGrid = document.getElementById("kb-grid");

  // -------------------------------------------------------------
  // 1. Initial Health Check & Load Applications
  // -------------------------------------------------------------
  async function checkHealth() {
    try {
      const res = await fetch("/api/v1/health");
      if (res.ok) {
        const data = await res.json();
        pipelineStatus.textContent = "RAG Engine: Ready";
        vectorBadge.textContent = data.vector_count || "20";
      }
    } catch (err) {
      pipelineStatus.textContent = "Engine Offline";
      console.error("Health check error:", err);
    }
  }

  async function loadApplications() {
    try {
      const res = await fetch("/api/v1/applications");
      if (res.ok) {
        const data = await res.json();
        gitApps = data.applications || [];
        renderGitRepositories(gitApps);
      }
    } catch (err) {
      console.error("Failed to load applications list:", err);
    }
  }

  checkHealth();
  loadApplications();

  // -------------------------------------------------------------
  // 2. Navigation Tabs
  // -------------------------------------------------------------
  navTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      navTabs.forEach((t) => t.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");

      if (targetId === "kb-tab" && kbTickets.length === 0) {
        loadKnowledgeBase();
      }
      if (targetId === "git-tab" && gitApps.length === 0) {
        loadApplications();
      }
    });
  });

  // -------------------------------------------------------------
  // 3. Quick Presets (Historical & Git Stacktrace)
  // -------------------------------------------------------------
  const presets = {
    "git-auth": {
      number: "INC-7001",
      app: "AuthService",
      title: "KeyError: 'user' when validating expired session payload",
      details: `Traceback (most recent call last):
  File "AuthService/token_handler.py", line 10, in validate_user_session
    user_id = session_data["user"]["id"]
KeyError: 'user'

Customer received 500 Internal Server Error when resuming session from mobile webview.`,
    },
    "git-payment": {
      number: "INC-7002",
      app: "PaymentGateway",
      title: "ZeroDivisionError in currency conversion during refund calculation",
      details: `Traceback (most recent call last):
  File "PaymentGateway/processor.py", line 15, in process_refund
    converted_amount = refund_amount / rate
ZeroDivisionError: division by zero

Merchant initiated a partial refund for multi-currency transaction TX-9921 where exchange_rate field evaluated to 0.`,
    },
    "git-index": {
      number: "INC-7003",
      app: "AuthService",
      title: "IndexError: list index out of range in decode_auth_header",
      details: `Traceback (most recent call last):
  File "AuthService/token_handler.py", line 24, in decode_auth_header
    token = parts[1]
IndexError: list index out of range

Client sent malformed Authorization header with no space separator between scheme and token.`,
    },
    "hist-auth": {
      number: "INC-7004",
      app: "AuthService",
      title: "Unable to log in after password reset",
      details: "User reset password via the email link but still receives invalid credentials error on web portal after multiple attempts.",
    },
    "hist-billing": {
      number: "INC-7005",
      app: "BillingEngine",
      title: "Invoice shows incorrect tax rate for region",
      details: "Customer invoice INV-8812 applied an 18% tax rate instead of expected 8% for their registered billing region.",
    },
  };

  presetChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const key = chip.getAttribute("data-preset");
      const p = presets[key];
      if (p) {
        ticketNumberInput.value = p.number;
        applicationNameInput.value = p.app;
        ticketTitleInput.value = p.title;
        ticketDetailsInput.value = p.details;
      }
    });
  });

  btnResetSingle.addEventListener("click", () => {
    singleForm.reset();
    singleEmptyState.classList.remove("hidden");
    singleResultsContainer.classList.add("hidden");
  });

  // -------------------------------------------------------------
  // 4. Single Ticket Analysis Submission
  // -------------------------------------------------------------
  singleForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const ticketNumber = ticketNumberInput.value.trim() || `INC-${Math.floor(1000 + Math.random() * 9000)}`;
    const appName = applicationNameInput.value;
    const title = ticketTitleInput.value.trim();
    const details = ticketDetailsInput.value.trim();

    if (!title && !details) {
      showToast("Please enter an issue title or description.");
      return;
    }

    setLoading(btnAnalyzeSingle, true);

    try {
      const resp = await fetch("/api/v1/tickets/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticket_number: ticketNumber,
          application_name: appName === "Other" ? null : appName,
          title: title,
          description: details,
        }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP Error ${resp.status}`);
      }

      const data = await resp.json();
      renderSingleResult(ticketNumber, appName, title, details, data);
    } catch (err) {
      console.error("Single triage error:", err);
      showToast("Failed to analyze ticket. Please check backend status.");
    } finally {
      setLoading(btnAnalyzeSingle, false);
    }
  });

  function renderSingleResult(ticketNumber, appName, title, details, data) {
    singleEmptyState.classList.add("hidden");
    singleResultsContainer.classList.remove("hidden");

    resTicketId.textContent = `TICKET #${ticketNumber}`;
    resAppTag.textContent = data.application_name || appName || "General";
    resTitle.textContent = title || details.slice(0, 80);

    // Channel badge
    const isGit = Boolean(data.code_analysis);
    resChannelBadge.textContent = data.source_channel || (isGit ? "Git Code Analysis" : "Ticket History RAG");
    resChannelBadge.className = `channel-badge ${isGit ? "git" : ""}`;

    const cls = data.classification || {};
    const cat = cls.predicted_category || "Technical Issue";
    const pri = cls.predicted_priority || "Medium";

    resCategory.textContent = cat;
    resCatConf.textContent = `${Math.round((cls.category_confidence || 0) * 100)}% conf`;

    resPriority.textContent = pri;
    resPriority.className = `badge badge-priority ${pri.toLowerCase()}`;
    resPriConf.textContent = `${Math.round((cls.priority_confidence || 0) * 100)}% conf`;

    // Dominant Topics
    resTopics.innerHTML = "";
    if (cls.dominant_topics && cls.dominant_topics.length > 0) {
      cls.dominant_topics.forEach((top) => {
        const tag = document.createElement("span");
        tag.className = "topic-tag";
        tag.textContent = top;
        resTopics.appendChild(tag);
      });
    } else {
      resTopics.innerHTML = '<span class="topic-tag">general</span>';
    }

    // Git Code Analysis Card
    if (data.code_analysis) {
      const ca = data.code_analysis;
      resGitBox.classList.remove("hidden");
      gitRepoUrl.textContent = ca.repo_url || `github.com/org/${ca.application_name.toLowerCase()}`;
      gitFileLoc.textContent = `${ca.file_path}:${ca.line_number}`;
      gitErrorType.textContent = `${ca.error_type}: ${ca.error_message || ""}`;
      gitRootCauseText.textContent = ca.root_cause || "Root cause identified from source AST analysis.";

      if (ca.code_context) {
        document.getElementById("git-code-wrapper").classList.remove("hidden");
        gitCodeContext.textContent = ca.code_context;
      } else {
        document.getElementById("git-code-wrapper").classList.add("hidden");
      }

      gitPatchCode.textContent = ca.suggested_fix || "// Code patch generated.";
    } else {
      resGitBox.classList.add("hidden");
    }

    // Recommended Resolution
    resResolution.textContent = data.recommended_resolution || "No suggested resolution generated.";
    resRecConf.textContent = `${Math.round((data.recommendation_confidence || 0) * 100)}%`;

    // Similar Tickets
    resSimilarList.innerHTML = "";
    if (data.similar_tickets && data.similar_tickets.length > 0) {
      data.similar_tickets.slice(0, 3).forEach((sim) => {
        const item = document.createElement("div");
        item.className = "similar-item";
        item.innerHTML = `
          <div class="similar-item-header">
            <span class="similar-title">${escapeHtml(sim.id)} - ${escapeHtml(sim.title)}</span>
            <span class="similar-score">${Math.round(sim.similarity_score * 100)}% match</span>
          </div>
          <div class="similar-resolution"><strong>Historical Resolution:</strong> ${escapeHtml(sim.resolution || "N/A")}</div>
        `;
        resSimilarList.appendChild(item);
      });
    } else {
      resSimilarList.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No historical tickets above similarity threshold (Git Codebase analysis applied).</p>';
    }

    // Reasoning Trace
    resReasoningList.innerHTML = "";
    if (data.reasoning && data.reasoning.length > 0) {
      data.reasoning.forEach((step) => {
        const li = document.createElement("li");
        li.textContent = step;
        resReasoningList.appendChild(li);
      });
    }
  }

  // Copy resolution button
  btnCopyResolution.addEventListener("click", () => {
    const text = resResolution.textContent;
    navigator.clipboard.writeText(text).then(() => {
      copyToast.classList.remove("hidden");
      setTimeout(() => copyToast.classList.add("hidden"), 2000);
    });
  });

  // -------------------------------------------------------------
  // 5. Batch CSV Processing (with Application & Stacktraces)
  // -------------------------------------------------------------
  csvDropzone.addEventListener("click", () => csvFileInput.click());

  csvDropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    csvDropzone.classList.add("dragover");
  });

  csvDropzone.addEventListener("dragleave", () => {
    csvDropzone.classList.remove("dragover");
  });

  csvDropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    csvDropzone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleCsvFileSelect(e.dataTransfer.files[0]);
    }
  });

  csvFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleCsvFileSelect(e.target.files[0]);
    }
  });

  function handleCsvFileSelect(file) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showToast("Please select a valid .csv file.");
      return;
    }
    selectedCsvFile = file;
    selectedFilename.textContent = file.name;
    selectedFilesize.textContent = formatBytes(file.size);
    csvDropzone.classList.add("hidden");
    fileSelectedBar.classList.remove("hidden");
  }

  btnClearCsv.addEventListener("click", () => {
    selectedCsvFile = null;
    csvFileInput.value = "";
    fileSelectedBar.classList.add("hidden");
    csvDropzone.classList.remove("hidden");
  });

  // Load Demo Batch Sample
  btnLoadDemoBatch.addEventListener("click", () => {
    const sampleCsvContent = `ticket_number,application_name,title,issue_details
INC-8001,AuthService,KeyError 'user' in session validation,"File ""AuthService/token_handler.py"", line 10, in validate_user_session\n    user_id = session_data[""user""][""id""]\nKeyError: 'user'"
INC-8002,PaymentGateway,ZeroDivisionError during refund,"File ""PaymentGateway/processor.py"", line 15, in process_refund\n    converted_amount = refund_amount / rate\nZeroDivisionError: division by zero"
INC-8003,BillingEngine,Incorrect tax jurisdiction calculation,"Customer's latest invoice applied an 18% tax rate instead of the expected 8% based on their billing region."
INC-8004,AuthService,IndexError in bearer token parsing,"File ""AuthService/token_handler.py"", line 24, in decode_auth_header\n    token = parts[1]\nIndexError: list index out of range"
INC-8005,MobileAppBackend,Mobile app crashing on large attachment upload,"Mobile app crashes consistently when a user attempts to upload files larger than 50MB from attachments."
INC-8006,BillingEngine,Tax jurisdiction missing key error,"File ""BillingEngine/tax_calculator.py"", line 12, in calculate_regional_tax\n    tax_percentage = custom_rates[region_code]\nKeyError: 'EU-FR'"`;

    const blob = new Blob([sampleCsvContent], { type: "text/csv" });
    const file = new File([blob], "demo_support_tickets_with_git.csv", { type: "text/csv" });
    handleCsvFileSelect(file);
    showToast("Loaded demo batch sample with Git repo applications!");
  });

  // Process Batch
  btnProcessBatch.addEventListener("click", async () => {
    if (!selectedCsvFile) return;

    setLoading(btnProcessBatch, true);
    batchLoader.classList.remove("hidden");
    batchResultsWrapper.classList.add("hidden");

    const formData = new FormData();
    formData.append("file", selectedCsvFile);

    try {
      const resp = await fetch("/api/v1/tickets/batch-csv", {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned ${resp.status}`);
      }

      const data = await resp.json();
      batchResults = data.results || [];
      renderBatchResults(data);
      showToast(`Processed ${data.total_tickets} tickets successfully (${data.git_code_analyses_count} Git code analyses triggered)!`);
    } catch (err) {
      console.error("Batch processing error:", err);
      showToast(`Batch processing failed: ${err.message}`);
    } finally {
      setLoading(btnProcessBatch, false);
      batchLoader.classList.add("hidden");
    }
  });

  function renderBatchResults(data) {
    batchResultsWrapper.classList.remove("hidden");

    // Metrics
    batchMetricTotal.textContent = data.total_tickets;
    batchMetricConf.textContent = `${Math.round(data.average_confidence * 100)}%`;
    batchMetricGitCount.textContent = data.git_code_analyses_count || 0;

    const priSummary = data.priority_summary || {};
    const criticalCount = (priSummary["Critical"] || 0) + (priSummary["High"] || 0);
    batchMetricCritical.textContent = criticalCount;

    // Populate Category Filter dropdown
    const catSummary = data.category_summary || {};
    batchFilterCat.innerHTML = '<option value="">All Categories</option>';
    Object.keys(catSummary).forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = `${c} (${catSummary[c]})`;
      batchFilterCat.appendChild(opt);
    });

    applyBatchFilters();
  }

  function applyBatchFilters() {
    const query = batchSearchInput.value.toLowerCase().trim();
    const catFilter = batchFilterCat.value;
    const priFilter = batchFilterPriority.value;

    const filtered = batchResults.filter((item) => {
      const matchesSearch =
        !query ||
        (item.ticket_number && item.ticket_number.toLowerCase().includes(query)) ||
        (item.application_name && item.application_name.toLowerCase().includes(query)) ||
        (item.title && item.title.toLowerCase().includes(query)) ||
        (item.description && item.description.toLowerCase().includes(query)) ||
        (item.recommended_resolution && item.recommended_resolution.toLowerCase().includes(query));

      const matchesCat = !catFilter || item.predicted_category === catFilter;
      const matchesPri = !priFilter || item.predicted_priority === priFilter;

      return matchesSearch && matchesCat && matchesPri;
    });

    renderBatchTable(filtered);
  }

  batchSearchInput.addEventListener("input", applyBatchFilters);
  batchFilterCat.addEventListener("change", applyBatchFilters);
  batchFilterPriority.addEventListener("change", applyBatchFilters);

  function renderBatchTable(items) {
    batchTableBody.innerHTML = "";

    if (items.length === 0) {
      batchTableBody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align:center; padding: 40px; color: var(--text-muted);">
            No tickets match the selected filters.
          </td>
        </tr>
      `;
      return;
    }

    items.forEach((item, idx) => {
      const tr = document.createElement("tr");
      const pri = item.predicted_priority || "Medium";
      const conf = Math.round(item.recommendation_confidence * 100);
      const isGit = item.code_analysis_applied;

      tr.innerHTML = `
        <td><span class="table-ticket-id">${escapeHtml(item.ticket_number || `T-${idx + 1}`)}</span></td>
        <td>
          <span class="table-app-badge">${escapeHtml(item.application_name || "General")}</span>
          ${isGit ? '<span style="font-size:0.7rem; color:#be185d; display:block; font-weight:700;">🐙 Git Fix</span>' : ''}
        </td>
        <td>
          <div class="table-summary">${escapeHtml(item.title || "No Title")}</div>
          <div class="table-desc-preview">${escapeHtml(item.description)}</div>
        </td>
        <td><span class="badge badge-category">${escapeHtml(item.predicted_category)}</span></td>
        <td><span class="badge badge-priority ${pri.toLowerCase()}">${escapeHtml(pri)}</span></td>
        <td><div class="table-resolution">${escapeHtml(item.recommended_resolution)}</div></td>
        <td><strong>${conf}%</strong></td>
        <td style="text-align: center;">
          <button type="button" class="btn btn-sm btn-outline btn-view-detail" data-index="${batchResults.indexOf(item)}">View</button>
        </td>
      `;
      batchTableBody.appendChild(tr);
    });

    // Attach click listeners to "View" buttons
    document.querySelectorAll(".btn-view-detail").forEach((btn) => {
      btn.addEventListener("click", () => {
        const index = parseInt(btn.getAttribute("data-index"), 10);
        const item = batchResults[index];
        if (item) {
          openDetailModal(item);
        }
      });
    });
  }

  // Export Results to CSV
  btnExportResultsCsv.addEventListener("click", () => {
    if (batchResults.length === 0) {
      showToast("No batch results to export.");
      return;
    }

    const headers = [
      "ticket_number",
      "application_name",
      "title",
      "description",
      "predicted_category",
      "predicted_priority",
      "category_confidence",
      "priority_confidence",
      "recommended_resolution",
      "recommendation_confidence",
      "git_code_analysis_applied",
      "git_offending_file",
      "git_line_number",
      "git_error_type",
    ];

    const rows = batchResults.map((r) => {
      const ca = r.code_analysis;
      return [
        `"${(r.ticket_number || "").replace(/"/g, '""')}"`,
        `"${(r.application_name || "").replace(/"/g, '""')}"`,
        `"${(r.title || "").replace(/"/g, '""')}"`,
        `"${(r.description || "").replace(/"/g, '""')}"`,
        `"${(r.predicted_category || "").replace(/"/g, '""')}"`,
        `"${(r.predicted_priority || "").replace(/"/g, '""')}"`,
        r.category_confidence,
        r.priority_confidence,
        `"${(r.recommended_resolution || "").replace(/"/g, '""')}"`,
        r.recommendation_confidence,
        r.code_analysis_applied ? "YES" : "NO",
        ca ? `"${ca.file_path}"` : '""',
        ca ? ca.line_number : "",
        ca ? `"${ca.error_type}"` : '""',
      ];
    });

    const csvContent = [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `ticket_triage_results_with_git_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("Exported results to CSV!");
  });

  // -------------------------------------------------------------
  // 6. Detail Modal (Showing Code Context & Patches)
  // -------------------------------------------------------------
  function openDetailModal(item) {
    modalTicketId.textContent = `Ticket Triage Detail: ${item.ticket_number || "Ticket"}`;
    const pri = item.predicted_priority || "Medium";
    const ca = item.code_analysis;

    modalBody.innerHTML = `
      <div style="margin-bottom: 16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <h4 style="font-size: 1.1rem;">${escapeHtml(item.title || "No title")}</h4>
          <span class="app-tag">${escapeHtml(item.application_name || "General")}</span>
        </div>
        <p style="font-size: 0.875rem; color: var(--text-muted); white-space:pre-wrap;">${escapeHtml(item.description)}</p>
      </div>

      <div class="predictions-card" style="margin-bottom: 16px;">
        <div class="pred-item">
          <div class="pred-label">Predicted Category</div>
          <div class="pred-val-row">
            <span class="badge badge-category">${escapeHtml(item.predicted_category)}</span>
            <span class="conf-pill">${Math.round(item.category_confidence * 100)}%</span>
          </div>
        </div>
        <div class="pred-item">
          <div class="pred-label">Predicted Priority</div>
          <div class="pred-val-row">
            <span class="badge badge-priority ${pri.toLowerCase()}">${escapeHtml(pri)}</span>
            <span class="conf-pill">${Math.round(item.priority_confidence * 100)}%</span>
          </div>
        </div>
      </div>

      ${
        ca
          ? `
        <div class="git-analysis-box" style="margin-bottom:16px;">
          <div class="git-box-header">
            <div class="git-box-title">
              <span class="git-icon">🐙</span>
              <h3>Git Code Analysis & Root Cause</h3>
            </div>
            <span class="git-repo-pill">${escapeHtml(ca.repo_url || ca.application_name)}</span>
          </div>
          <div class="git-meta-bar">
            <div class="git-meta-item">
              <span>Location:</span>
              <code>${escapeHtml(ca.file_path)}:${ca.line_number}</code>
            </div>
            <div class="git-meta-item">
              <span>Exception:</span>
              <span class="error-badge">${escapeHtml(ca.error_type)}: ${escapeHtml(ca.error_message || "")}</span>
            </div>
          </div>
          <div class="git-root-cause">
            <strong>Root Cause:</strong>
            <p>${escapeHtml(ca.root_cause || "")}</p>
          </div>
          ${
            ca.code_context
              ? `
            <div class="git-code-wrapper">
              <div class="code-header">Source Code Context</div>
              <pre class="code-block"><code>${escapeHtml(ca.code_context)}</code></pre>
            </div>
          `
              : ""
          }
          <div class="git-patch-wrapper">
            <div class="code-header">Suggested Code Patch</div>
            <pre class="patch-block"><code>${escapeHtml(ca.suggested_fix || "")}</code></pre>
          </div>
        </div>
      `
          : `
        <div class="recommendation-card" style="margin-bottom: 16px;">
          <div class="rec-header">
            <div class="rec-title-group">
              <span class="rec-icon">💡</span>
              <h3>Recommended Resolution</h3>
            </div>
            <div class="rec-confidence">
              Match Confidence: <strong>${Math.round(item.recommendation_confidence * 100)}%</strong>
            </div>
          </div>
          <div class="rec-body">${escapeHtml(item.recommended_resolution)}</div>
        </div>
      `
      }

      ${
        item.reasoning && item.reasoning.length > 0
          ? `
        <div style="background: var(--bg-subtle); padding: 14px; border-radius: 8px; border: 1px solid var(--border-color);">
          <strong style="font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase;">AI Reasoning Trail:</strong>
          <ul style="margin-top: 8px; padding-left: 18px; font-size: 0.825rem; color: var(--text-muted); line-height: 1.6;">
            ${item.reasoning.map((r) => `<li>${escapeHtml(r)}</li>`).join("")}
          </ul>
        </div>
      `
          : ""
      }
    `;

    detailModal.classList.remove("hidden");
  }

  btnCloseModal.addEventListener("click", () => detailModal.classList.add("hidden"));
  detailModal.addEventListener("click", (e) => {
    if (e.target === detailModal) detailModal.classList.add("hidden");
  });

  // -------------------------------------------------------------
  // 7. Git Repositories Tab
  // -------------------------------------------------------------
  function renderGitRepositories(apps) {
    if (!gitReposGrid) return;
    gitReposGrid.innerHTML = "";

    apps.forEach((app) => {
      const card = document.createElement("div");
      card.className = "repo-card";
      card.innerHTML = `
        <div class="repo-header">
          <span class="repo-name">${escapeHtml(app.name)}</span>
          <span class="repo-lang">${escapeHtml(app.language || "Python")}</span>
        </div>
        <div class="repo-url">🔗 ${escapeHtml(app.repo_url)}</div>
        <div class="repo-desc">${escapeHtml(app.description)}</div>
      `;
      gitReposGrid.appendChild(card);
    });
  }

  // -------------------------------------------------------------
  // 8. Knowledge Base Tab & Ingestion
  // -------------------------------------------------------------
  async function loadKnowledgeBase() {
    try {
      const resp = await fetch("/api/v1/tickets/list");
      if (resp.ok) {
        const data = await resp.json();
        kbTickets = data.tickets || [];
        renderKnowledgeBase(kbTickets);
      }
    } catch (err) {
      console.error("Failed to load knowledge base:", err);
    }
  }

  function renderKnowledgeBase(tickets) {
    kbGrid.innerHTML = "";
    if (tickets.length === 0) {
      kbGrid.innerHTML = '<p class="text-muted">No tickets found in index.</p>';
      return;
    }

    tickets.forEach((t) => {
      const card = document.createElement("div");
      card.className = "kb-card";
      const pri = t.priority || "Medium";

      card.innerHTML = `
        <div class="kb-header">
          <span class="kb-id">${escapeHtml(t.id)}</span>
          <span class="badge badge-priority ${pri.toLowerCase()}">${escapeHtml(pri)}</span>
        </div>
        <div class="kb-title">${escapeHtml(t.title)}</div>
        <div class="kb-desc">${escapeHtml(t.description)}</div>
        <div class="kb-res"><strong>Resolution:</strong> ${escapeHtml(t.resolution || "None")}</div>
      `;
      kbGrid.appendChild(card);
    });
  }

  kbSearchInput.addEventListener("input", () => {
    const q = kbSearchInput.value.toLowerCase().trim();
    const filtered = kbTickets.filter(
      (t) =>
        t.id.toLowerCase().includes(q) ||
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        (t.resolution && t.resolution.toLowerCase().includes(q))
    );
    renderKnowledgeBase(filtered);
  });

  // Ingest Modal
  btnOpenIngestModal.addEventListener("click", () => ingestModal.classList.remove("hidden"));
  btnCloseIngestModal.addEventListener("click", () => ingestModal.classList.add("hidden"));
  btnCancelIngest.addEventListener("click", () => ingestModal.classList.add("hidden"));

  ingestForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      title: document.getElementById("ingest-title").value.trim(),
      application_name: document.getElementById("ingest-app").value.trim() || null,
      description: document.getElementById("ingest-desc").value.trim(),
      category: document.getElementById("ingest-category").value,
      priority: document.getElementById("ingest-priority").value,
      resolution: document.getElementById("ingest-resolution").value.trim(),
      tags: document
        .getElementById("ingest-tags")
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };

    try {
      const resp = await fetch("/api/v1/tickets/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (resp.ok) {
        showToast("Ticket ingested into Knowledge Base & FAISS index!");
        ingestForm.reset();
        ingestModal.classList.add("hidden");
        loadKnowledgeBase();
        checkHealth();
      } else {
        showToast("Failed to ingest ticket.");
      }
    } catch (err) {
      console.error("Ingest error:", err);
      showToast("Error ingesting ticket.");
    }
  });

  // -------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------
  function setLoading(btn, isLoading) {
    const spinner = btn.querySelector(".spinner");
    const text = btn.querySelector(".btn-text");
    if (isLoading) {
      btn.disabled = true;
      if (spinner) spinner.classList.remove("hidden");
    } else {
      btn.disabled = false;
      if (spinner) spinner.classList.add("hidden");
    }
  }

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.remove("hidden");
    setTimeout(() => toast.classList.add("hidden"), 3000);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }
});
