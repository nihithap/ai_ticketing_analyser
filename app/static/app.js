/**
 * AI Support Ticket Triage & Resolution Assistant Frontend Logic
 */
document.addEventListener("DOMContentLoaded", () => {
  // State
  let batchResults = [];
  let kbTickets = [];
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
  const ticketTitleInput = document.getElementById("ticket-title");
  const ticketDetailsInput = document.getElementById("ticket-details");
  const btnAnalyzeSingle = document.getElementById("btn-analyze-single");
  const btnResetSingle = document.getElementById("btn-reset-single");
  const singleEmptyState = document.getElementById("single-empty-state");
  const singleResultsContainer = document.getElementById("single-results-container");

  // Single Results Elements
  const resTicketId = document.getElementById("res-ticket-id");
  const resTitle = document.getElementById("res-title");
  const resCategory = document.getElementById("res-category");
  const resCatConf = document.getElementById("res-cat-conf");
  const resPriority = document.getElementById("res-priority");
  const resPriConf = document.getElementById("res-pri-conf");
  const resTopics = document.getElementById("res-topics");
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
  const batchMetricCritical = document.getElementById("batch-metric-critical");
  const batchMetricTopCat = document.getElementById("batch-metric-top-cat");
  const batchSearchInput = document.getElementById("batch-search-input");
  const batchFilterCat = document.getElementById("batch-filter-cat");
  const batchFilterPriority = document.getElementById("batch-filter-priority");
  const batchTableBody = document.getElementById("batch-table-body");
  const btnExportResultsCsv = document.getElementById("btn-export-results-csv");

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
  // 1. Initial Health Check
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
  checkHealth();

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
    });
  });

  // -------------------------------------------------------------
  // 3. Single Ticket Presets
  // -------------------------------------------------------------
  const presets = {
    auth: {
      number: "INC-2041",
      title: "Unable to log in after password reset",
      details: "User reset password via the email link but still receives invalid credentials error on web portal. User verified caps lock is off.",
    },
    billing: {
      number: "INC-2042",
      title: "Invoice shows incorrect tax amount",
      details: "Customer was charged 18% tax rate on invoice INV-9041 instead of standard 8% for their billing jurisdiction.",
    },
    crash: {
      number: "INC-2043",
      title: "App crashes when uploading large files",
      details: "Mobile app crashes consistently when attempting to upload video attachments larger than 50MB in the support chat.",
    },
    vpn: {
      number: "INC-2044",
      title: "VPN connection drops every 10 minutes with error 691",
      details: "Remote engineer connection to the US-East gateway drops intermittently. Client displays authentication failed error 691.",
    },
  };

  presetChips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const key = chip.getAttribute("data-preset");
      const p = presets[key];
      if (p) {
        ticketNumberInput.value = p.number;
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
          title: title,
          description: details,
        }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP Error ${resp.status}`);
      }

      const data = await resp.json();
      renderSingleResult(ticketNumber, title, details, data);
    } catch (err) {
      console.error("Single triage error:", err);
      showToast("Failed to analyze ticket. Please check backend status.");
    } finally {
      setLoading(btnAnalyzeSingle, false);
    }
  });

  function renderSingleResult(ticketNumber, title, details, data) {
    singleEmptyState.classList.add("hidden");
    singleResultsContainer.classList.remove("hidden");

    resTicketId.textContent = `TICKET #${ticketNumber}`;
    resTitle.textContent = title || details.slice(0, 80);

    const cls = data.classification || {};
    const cat = cls.predicted_category || "General Inquiry";
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

    // Recommendation
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
      resSimilarList.innerHTML = '<p class="text-muted" style="font-size:0.85rem;">No historical tickets above similarity threshold.</p>';
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
  // 5. Batch CSV Processing
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
    const sampleCsvContent = `ticket_number,title,issue_details
INC-5001,Cannot connect to company VPN,User receives error 691 when attempting to authenticate on the US-East VPN server gateway.
INC-5002,Invoice tax amount calculation error,Customer invoice applied 18 percent tax instead of standard 8 percent regional tax rate.
INC-5003,Mobile app crashing on video upload,iOS app crashes every time user tries to upload an MP4 video over 50MB.
INC-5004,Password reset link not received in email,Customer requested password reset link three times but verification email never arrived in inbox.
INC-5005,Database report export 504 gateway timeout,Monthly summary CSV export times out after 60 seconds with 504 gateway error.
INC-5006,Requesting dark mode theme feature,User is asking for dark mode theme support in the desktop client settings.
INC-5007,Suspicious login attempts detected from unknown IP,Security alert triggered for multiple failed SSH attempts from foreign IP address.`;

    const blob = new Blob([sampleCsvContent], { type: "text/csv" });
    const file = new File([blob], "demo_support_tickets_batch.csv", { type: "text/csv" });
    handleCsvFileSelect(file);
    showToast("Loaded demo support tickets batch sample!");
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
      showToast(`Processed ${data.total_tickets} tickets successfully!`);
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

    const priSummary = data.priority_summary || {};
    const criticalCount = (priSummary["Critical"] || 0) + (priSummary["High"] || 0);
    batchMetricCritical.textContent = criticalCount;

    const catSummary = data.category_summary || {};
    let topCat = "-";
    let maxCount = -1;
    for (const [k, v] of Object.entries(catSummary)) {
      if (v > maxCount) {
        maxCount = v;
        topCat = k;
      }
    }
    batchMetricTopCat.textContent = topCat;

    // Populate Category Filter dropdown
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
          <td colspan="7" style="text-align:center; padding: 40px; color: var(--text-muted);">
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

      tr.innerHTML = `
        <td><span class="table-ticket-id">${escapeHtml(item.ticket_number || `T-${idx + 1}`)}</span></td>
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
      "title",
      "description",
      "predicted_category",
      "predicted_priority",
      "category_confidence",
      "priority_confidence",
      "recommended_resolution",
      "recommendation_confidence",
      "top_similar_ticket_id",
      "top_similarity_score",
    ];

    const rows = batchResults.map((r) => [
      `"${(r.ticket_number || "").replace(/"/g, '""')}"`,
      `"${(r.title || "").replace(/"/g, '""')}"`,
      `"${(r.description || "").replace(/"/g, '""')}"`,
      `"${(r.predicted_category || "").replace(/"/g, '""')}"`,
      `"${(r.predicted_priority || "").replace(/"/g, '""')}"`,
      r.category_confidence,
      r.priority_confidence,
      `"${(r.recommended_resolution || "").replace(/"/g, '""')}"`,
      r.recommendation_confidence,
      `"${(r.top_similar_ticket_id || "").replace(/"/g, '""')}"`,
      r.top_similarity_score || "",
    ]);

    const csvContent = [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `ticket_triage_results_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("Exported results to CSV!");
  });

  // -------------------------------------------------------------
  // 6. Detail Modal
  // -------------------------------------------------------------
  function openDetailModal(item) {
    modalTicketId.textContent = `Ticket Triage Detail: ${item.ticket_number || "Ticket"}`;
    const pri = item.predicted_priority || "Medium";

    modalBody.innerHTML = `
      <div style="margin-bottom: 16px;">
        <h4 style="font-size: 1.1rem; margin-bottom: 6px;">${escapeHtml(item.title || "No title")}</h4>
        <p style="font-size: 0.875rem; color: var(--text-muted);">${escapeHtml(item.description)}</p>
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
  // 7. Knowledge Base Tab & Ingestion
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
