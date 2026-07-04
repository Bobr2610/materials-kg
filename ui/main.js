var state = {
  files: [],
  selected: new Set(),
  sourceFilter: "",
  sourceLimit: UI_CONFIG.sourcePageSize,
  total: 0,
  overview: null,
  destructiveApiEnabled: false
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

function removeHero() { $("hero")?.remove(); }

function addMsg(role, html) {
  removeHero();
  const el = document.createElement("article");
  el.className = "msg " + role;
  el.innerHTML = html;
  $("chatBody").appendChild(el);
  $("chatBody").scrollTop = $("chatBody").scrollHeight;
}

function chipList(rows) {
  if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">' + UI_TEXT.noData + '</span>';
  return '<div class="chips">' + rows.slice(0, UI_CONFIG.maxChipRows).map(r =>
    '<span class="chip">' + escapeHtml(r.canonical_name) + ' <span class="kind">' + escapeHtml(r.kind) + "</span></span>"
  ).join("") + "</div>";
}

function listBlock(rows, render, empty) {
  if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">' + escapeHtml(empty) + "</span>";
  return '<ul class="mini-list">' + rows.slice(0, UI_CONFIG.maxListRows).map(r => "<li>" + render(r) + "</li>").join("") + "</ul>";
}

function tableBlock(rows) {
  if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">' + UI_TEXT.noMeasurements + '</span>';
  return '<table class="data"><thead><tr><th>Значение</th><th>Единица</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>' +
    rows.slice(0, UI_CONFIG.maxTableRows).map(r => "<tr><td>" + escapeHtml(r.value??"n/a") + "</td><td>" + escapeHtml(r.unit??"") + "</td><td>" + escapeHtml(r.confidence) + "</td><td>" + escapeHtml(r.evidence_id) + "</td></tr>").join("") +
    "</tbody></table>";
}

function renderCitations(citations) {
  if (!citations?.length) return "";
  const items = citations.slice(0, UI_CONFIG.maxCitations).map(c =>
    '<div class="cite-item"><b>[' + escapeHtml(c.source_kind) + '] ' + escapeHtml(c.source_id) + "</b> — " + escapeHtml((c.fragment||"").substring(0,150)) + (c.fragment?.length > 150 ? "..." : "") + "</div>"
  ).join("");
  return '<div class="citations-block"><h3>' + UI_TEXT.citationsTitle + '</h3>' + items + "</div>";
}

function renderAnswer(data) {
  const w = (data.warnings||[]).map(r => '<span class="chip" style="border-color:#fdd835;background:#fffde7">' + escapeHtml(r) + "</span>").join("");
  const citations = renderCitations(data.citations);
  addMsg("assistant",
    '<div class="bubble">' + escapeHtml(data.answer||UI_TEXT.answerMissing) + "</div>" +
    (w ? '<div class="answer-card"><h3>Предупреждения</h3><div class="chips">' + w + "</div></div>" : "") +
    '<div class="answer-card"><h3>Сущности</h3>' + chipList(data.matched_entities) + "</div>" +
    '<div class="answer-card"><h3>Эксперименты</h3>' + listBlock(data.experiments, r => "<b>" + escapeHtml(r.canonical_name) + "</b><span>" + escapeHtml(r.id) + "</span>", UI_TEXT.noExperiments) + "</div>" +
    '<div class="answer-card"><h3>Измерения</h3>' + tableBlock(data.observations) + "</div>" +
    (citations ? '<div class="answer-card">' + citations + "</div>" : "")
  );
}

async function ask() {
  const q = $("question").value.trim();
  if (!q) return;
  $("sendQuestion").disabled = true;
  addMsg("user", '<div class="bubble">' + escapeHtml(q) + "</div>");
  $("question").value = "";
  $("question").style.height = "auto";
  try {
    const sourceIds = getSelectedSources();
    const payload = { question: q };
    if (sourceIds) payload.source_ids = sourceIds;
    const data = await postJson(UI_CONFIG.endpoints.queryAnswer, payload);
    renderAnswer(data);
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  } finally {
    $("sendQuestion").disabled = false;
  }
}

function clearChat() {
  $("menuPopover").classList.remove("open");
  $("chatBody").innerHTML =
    '<div class="hero" id="hero"><div class="hero-inner"><div class="hero-icon">&#9883;</div><h1>Фабрика гипотез</h1><p id="notebookMeta">Добавьте источники слева и задавайте вопросы в чате. Граф знаний строится только из загруженных данных.</p></div></div>';
}

function syncDestructiveActions() {
  const clearAll = $("clearAllSources");
  if (!clearAll) return;
  clearAll.hidden = !state.destructiveApiEnabled;
}

async function loadInitialState() {
  try {
    const r = await fetch(UI_CONFIG.endpoints.state);
    if (!r.ok) return;
    const data = await r.json();
    state.destructiveApiEnabled = Boolean(data.destructive_api_enabled);
    syncDestructiveActions();
    if (data.overview) state.overview = data.overview;
    if (data.source_files?.length) {
      mergeFiles(data.source_files);
      renderSourceList();
    } else {
      state.files = [];
      state.selected.clear();
      state.overview = null;
      renderSourceList();
    }
  } catch(e) { /* silent on startup */ }
}

function registerEventListeners() {
  $("addSources").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", e => { uploadFiles(Array.from(e.target.files)); e.target.value = ""; });
  $("sendQuestion").addEventListener("click", ask);
  $("question").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  $("question").addEventListener("input", function() { this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 120) + "px"; });
  $("graphToggle").addEventListener("click", () => {
    $("graphPanel").classList.toggle("open");
    if ($("graphPanel").classList.contains("open")) { buildLegendForNodes([]); loadGraph(); }
  });
  $("graphClose").addEventListener("click", closeGraphPanel);
  $("menuButton").addEventListener("click", e => { e.stopPropagation(); $("menuPopover").classList.toggle("open"); });
  $("loadTaskMaterials").addEventListener("click", loadTaskMaterials);
  $("clearAllSources").addEventListener("click", () => { $("menuPopover").classList.remove("open"); clearAllSources(); });
  $("clearChat").addEventListener("click", clearChat);
  $("sourceSearch").addEventListener("input", e => {
    state.sourceFilter = e.target.value;
    state.sourceLimit = UI_CONFIG.sourcePageSize;
    renderSourceList();
  });
  $("sources").addEventListener("change", e => {
    if (!e.target.classList.contains("source-check")) return;
    const name = e.target.dataset.name;
    if (!name) return;
    if (e.target.checked) state.selected.add(name);
    else state.selected.delete(name);
    setSourceStats();
    e.target.closest(".source-row")?.classList.toggle("is-muted", !e.target.checked);
    refreshGraphIfOpen();
  });
  $("sources").addEventListener("click", e => {
    const btn = e.target.closest(".source-delete");
    if (btn?.dataset.name) deleteSource(btn.dataset.name);
  });
  document.addEventListener("click", e => { if (!$("menuPopover").contains(e.target) && e.target !== $("menuButton")) $("menuPopover").classList.remove("open"); });
  let dragTimer;
  document.addEventListener("dragenter", e => { e.preventDefault(); clearTimeout(dragTimer); $("dropOverlay").classList.add("active"); });
  document.addEventListener("dragover", e => e.preventDefault());
  document.addEventListener("dragleave", e => { e.preventDefault(); dragTimer = setTimeout(() => $("dropOverlay").classList.remove("active"), 200); });
  document.addEventListener("drop", e => { e.preventDefault(); $("dropOverlay").classList.remove("active"); if (e.dataTransfer.files.length) uploadFiles(Array.from(e.dataTransfer.files)); });
  const fileInput = $("fileInput");
  if (fileInput) fileInput.accept = UI_CONFIG.acceptAttribute;
}

document.addEventListener("DOMContentLoaded", () => {
  registerEventListeners();
  syncDestructiveActions();
  buildLegend();
  loadInitialState();
});
