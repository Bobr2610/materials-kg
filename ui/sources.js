function formatSize(bytes) {
  bytes = Number(bytes || 0);
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function formatCount(n, one, few, many) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return n + " " + one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + " " + few;
  return n + " " + many;
}

function sourceType(file) {
  const ext = file.name?.split(".").pop();
  return String(ext || file.type || "unknown").toLowerCase();
}

function normalizeFile(file) {
  const name = file.name || "unnamed";
  const type = sourceType(file);
  return {
    name,
    size: Number(file.size || 0),
    type: UI_CONFIG.supportedTypes.includes(type) ? type : "unknown"
  };
}

function setSourceStats() {
  state.total = state.files.length;
  const selectedCount = state.files.filter(f => state.selected.has(f.name)).length;
  const totalText = formatCount(state.total, "источник", "источника", "источников");
  const selectedText = selectedCount + " выбрано";
  if ($("sourceNote")) $("sourceNote").textContent = state.total ? selectedText : "0 источников";
  if ($("sourceSummary")) $("sourceSummary").textContent = state.total ? selectedText + " из " + state.total : "0 выбрано";
}

function mergeFiles(files, selectNew = true) {
  const byName = new Map(state.files.map(f => [f.name, f]));
  files.map(normalizeFile).forEach(file => {
    const existing = byName.get(file.name);
    byName.set(file.name, existing ? { ...existing, ...file } : file);
    if (selectNew && !state.selected.has(file.name)) state.selected.add(file.name);
  });
  state.files = Array.from(byName.values()).sort((a, b) => a.name.localeCompare(b.name));
  setSourceStats();
}

function emptySourcesHtml() {
  return '<div class="source-empty" id="sourceEmpty"><div><div class="doc-icon"><svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg></div><strong>' + UI_TEXT.sourceEmptyTitle + '</strong><p>' + UI_TEXT.sourceEmptyBody + '</p></div></div>';
}

function getSelectedSources() {
  if (!state.files.length) return null;
  const selected = state.files.filter(f => state.selected.has(f.name)).map(f => f.name);
  if (selected.length === state.files.length) return null;
  return selected;
}

function renderSourceList() {
  const query = state.sourceFilter.trim().toLowerCase();
  const filtered = query
    ? state.files.filter(f => f.name.toLowerCase().includes(query) || sourceType(f).includes(query))
    : state.files;
  const visible = filtered.slice(0, state.sourceLimit);
  if (!state.files.length) {
    $("sources").innerHTML = emptySourcesHtml();
    setSourceStats();
    return;
  }
  if (!filtered.length) {
    $("sources").innerHTML = '<div class="source-empty"><div><strong>' + UI_TEXT.sourceNotFoundTitle + '</strong><p>' + UI_TEXT.sourceNotFoundBody + '</p></div></div>';
    setSourceStats();
    return;
  }
  $("sources").innerHTML = visible.map(f => {
    const t = sourceType(f);
    const checked = state.selected.has(f.name) ? " checked" : "";
    const muted = checked ? "" : " is-muted";
    const deleteButton = state.destructiveApiEnabled
      ? '<button class="source-delete" data-name="' + escapeHtml(f.name) + '" title="Удалить из базы">&times;</button>'
      : "";
    return '<div class="source-row' + muted + '"><input type="checkbox" class="source-check"' + checked + ' data-name="' + escapeHtml(f.name) + '">' +
      '<div class="source-icon ' + t + '">' + t.toUpperCase() + "</div>" +
      '<div class="source-info"><b title="' + escapeHtml(f.name) + '">' + escapeHtml(f.name) + "</b><span>" + formatSize(f.size) + "</span></div>" +
      deleteButton + "</div>";
  }).join("") + (filtered.length > visible.length
    ? '<button class="source-more" id="showMoreSources" type="button">Показать ещё ' + Math.min(UI_CONFIG.sourcePageSize, filtered.length - visible.length) + '</button>'
    : "");
  $("showMoreSources")?.addEventListener("click", () => {
    state.sourceLimit += UI_CONFIG.sourcePageSize;
    renderSourceList();
  });
  setSourceStats();
}

function renderSources(uploadResult, options = {}) {
  const uploaded = uploadResult.uploaded || [];
  if (uploaded.length) mergeFiles(uploaded);
  if (uploadResult.overview) state.overview = uploadResult.overview;
  renderSourceList();
}

function setUploadProgress(done, total, label) {
  const percent = total ? Math.round((done / total) * 100) : 0;
  $("uploadProgressText").textContent = label || ("Загружено " + done + " из " + total);
  $("uploadProgressFill").style.width = percent + "%";
}

async function uploadFiles(files) {
  if (!files.length) return;
  const uploadQueue = files.map(normalizeFile);
  mergeFiles(uploadQueue);
  renderSourceList();
  $("uploadProgress").classList.add("active");
  $("addSources").disabled = true;
  setUploadProgress(0, files.length, "Подготовка " + formatCount(files.length, "файл", "файла", "файлов"));
  const totals = { entities: 0, experiments: 0, documents: 0, llmStructured: 0, llmExtracted: 0, fallback: 0 };
  let lastOverview = null;
  let uploadedCount = 0;
  try {
    for (let offset = 0; offset < files.length; offset += UI_CONFIG.uploadBatchSize) {
      const batch = files.slice(offset, offset + UI_CONFIG.uploadBatchSize);
      const fd = new FormData();
      for (const f of batch) fd.append("files", f);
      setUploadProgress(uploadedCount, files.length, "Загрузка " + (offset + 1) + "-" + Math.min(offset + batch.length, files.length) + " из " + files.length);
      const r = await fetch(UI_CONFIG.endpoints.upload, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      const data = await r.json();
      uploadedCount += batch.length;
      totals.entities += data.reference?.entities || 0;
      totals.experiments += data.experiments?.experiments || 0;
      totals.documents += data.documents?.documents || 0;
      totals.llmStructured += data.ingestion?.llm_structured_files?.length || 0;
      totals.fallback += data.ingestion?.searchable_fallback_files?.length || 0;
      totals.llmExtracted += data.documents?.llm_extracted_experiments || 0;
      lastOverview = data.overview || lastOverview;
      renderSources(data, { notify: false });
      setUploadProgress(uploadedCount, files.length, "Загружено " + uploadedCount + " из " + files.length);
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    const counts = [];
    if (totals.entities) counts.push(totals.entities + " сущностей");
    if (totals.experiments) counts.push(totals.experiments + " экспериментов");
    if (totals.documents) counts.push(totals.documents + " документов");
    if (totals.llmStructured) counts.push("ИИ-нормализация: " + totals.llmStructured);
    if (totals.llmExtracted) counts.push("ИИ-извлечение: " + totals.llmExtracted);
    if (totals.fallback) counts.push("fallback: " + totals.fallback + " (ИИ не вернула структуру)");
    addMsg("assistant", '<div class="bubble">Готово: ' + formatCount(files.length, "файл", "файла", "файлов") + ". " + (counts.join(", ") || UI_TEXT.filesAccepted) + ".</div>");
    refreshGraphIfOpen();
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  } finally {
    $("uploadProgress").classList.remove("active");
    $("uploadProgressFill").style.width = "0%";
    $("addSources").disabled = false;
  }
}

async function loadTaskMaterials() {
  $("menuPopover").classList.remove("open");
  $("uploadProgress").classList.add("active");
  $("loadTaskMaterials").disabled = true;
  setUploadProgress(0, 1, "Постановка загрузки Task 1 в очередь");
  try {
    let job = await postJson(endpointWithParams(UI_CONFIG.endpoints.loadTaskMaterials, UI_CONFIG.taskMaterialsParams), {});
    addMsg("assistant", '<div class="bubble">Загрузка Task 1 запущена: ' + escapeHtml(job.job_id) + ".</div>");
    while (job.status === "queued" || job.status === "running") {
      const total = Math.max(Number(job.total_files || 0), 1);
      const done = Math.min(Number(job.processed_files || 0), total);
      setUploadProgress(done, total, (job.message || job.stage || "Загрузка Task 1") + " (" + done + "/" + total + ")");
      if (job.uploaded?.length) {
        mergeFiles(job.uploaded);
        renderSourceList();
      }
      await new Promise(resolve => setTimeout(resolve, 1200));
      const r = await fetch(UI_CONFIG.endpoints.loadTaskMaterialsJobBase + encodeURIComponent(job.job_id));
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      job = await r.json();
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Task 1 load failed");
    }
    const data = job.result || {};
    renderSources(data, { notify: false });
    setUploadProgress(1, 1, "Task 1 загружена");
    const unsupported = data.unsupported_files?.length ? " Неподдерживаемых файлов: " + data.unsupported_files.length + "." : "";
    const skipped = data.skipped_example_files?.length ? " Примеры пропущены: " + data.skipped_example_files.length + "." : "";
    const skippedFiles = data.skipped_files?.length ? " Файлы пропущены: " + data.skipped_files.length + "." : "";
    const warning = data.warnings?.length ? " " + data.warnings.map(escapeHtml).join(" ") : "";
    addMsg("assistant", '<div class="bubble">Материалы Task 1 загружены из ' + escapeHtml(data.task_materials_dir) + ". Документов: " + escapeHtml(data.documents_ingested || 0) + "." + skipped + skippedFiles + unsupported + warning + "</div>");
    refreshGraphIfOpen();
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  } finally {
    $("uploadProgress").classList.remove("active");
    $("uploadProgressFill").style.width = "0%";
    $("loadTaskMaterials").disabled = false;
  }
}

async function deleteSource(name) {
  if (!state.destructiveApiEnabled) return;
  try {
    const r = await fetch(UI_CONFIG.endpoints.sourceDeleteBase + encodeURIComponent(name), { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    const data = await r.json();
    state.files = state.files.filter(f => f.name !== name);
    state.selected.delete(name);
    if (!state.files.length) state.overview = null;
    setSourceStats();
    renderSourceList();
    addMsg("assistant", '<div class="bubble">Источник "' + escapeHtml(name) + '" удалён из базы. Убрано записей: ' + data.removed_records + ".</div>");
    refreshGraphIfOpen();
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  }
}

async function clearAllSources() {
  if (!state.destructiveApiEnabled) {
    $("menuPopover").classList.remove("open");
    return;
  }
  try {
    const r = await fetch(UI_CONFIG.endpoints.sources, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    const data = await r.json();
    state.files = [];
    state.selected.clear();
  state.overview = null;
  state.sourceLimit = UI_CONFIG.sourcePageSize;
  state.lastHypothesisResult = null;
  $("exportHypothesesJson").disabled = true;
  $("exportHypothesesCsv").disabled = true;
  $("exportHypothesesXlsx").disabled = true;
  $("exportHypothesesDocx").disabled = true;
  $("exportHypothesesPdf").disabled = true;
  setSourceStats();
  renderSourceList();
    addMsg("assistant", '<div class="bubble">' + UI_TEXT.allSourcesRemoved + "</div>");
    refreshGraphIfOpen();
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  }
}
