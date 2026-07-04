function scoreValue(v) {
  return Number(v || 0).toFixed(2);
}

function renderScoreGrid(score) {
  if (!score) return "";
  const rows = [
    ["Итог", score.final_score],
    ["Новизна", score.novelty],
    ["Риск", score.risk],
    ["Ценность", score.value],
    ["Данные", score.evidence_strength]
  ];
  return '<div class="score-grid">' + rows.map(([label, value]) =>
    '<div class="score-pill"><span>' + escapeHtml(label) + '</span><b>' + scoreValue(value) + '</b></div>'
  ).join("") + "</div>";
}

function renderStringList(rows, empty) {
  if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">' + escapeHtml(empty) + "</span>";
  return '<ul class="mini-list">' + rows.slice(0, UI_CONFIG.maxListRows).map(r => "<li><span>" + escapeHtml(r) + "</span></li>").join("") + "</ul>";
}

function renderIdChips(label, ids) {
  if (!ids?.length) return "";
  return '<div><b style="font-size:13px">' + escapeHtml(label) + '</b><div class="id-chip-list">' +
    ids.slice(0, UI_CONFIG.maxChipRows).map(id => '<span class="id-chip">' + escapeHtml(id) + '</span>').join("") +
    "</div></div>";
}

function hypothesisTypeLabel(type) {
  return ({
    coverage_gap: "пробел данных",
    observed_effect: "наблюдаемый эффект",
    literature_signal: "сигнал из литературы"
  })[type] || type || "гипотеза";
}

function renderKnowledgeSummary(data) {
  const s = data.knowledge_base_summary || {};
  const rubric = data.ranking_rubric || {};
  const bits = [
    "engine: " + (data.generation_engine || "n/a"),
    "llm: " + (data.llm_used || "n/a"),
    "observations: " + (s.observations || 0),
    "evidence: " + (s.evidence || 0),
    "text hits: " + (s.text_hits || 0),
    "data gaps: " + (s.data_gaps || 0)
  ];
  return '<div class="answer-card"><h3>База знаний для KPI</h3><div class="chips">' +
    bits.map(x => '<span class="chip">' + escapeHtml(x) + '</span>').join("") +
    '</div><span style="font-size:12px;color:#5f6368">Ранжирование: ' + escapeHtml(rubric.final_score_formula || "") + "</span></div>";
}

function renderAgentTrace(trace) {
  if (!trace?.length) return "";
  const rows = trace.slice(0, 12).map(item => {
    const label = item.event || item.tool || "trace";
    const detail = JSON.stringify(item);
    return '<div class="trace-row"><b>' + escapeHtml(label) + '</b><br>' + escapeHtml(detail) + '</div>';
  }).join("");
  return '<div class="answer-card"><h3>Agent trace</h3><div class="agent-trace">' + rows + "</div></div>";
}

function adjustmentFor(id) {
  return state.expertAdjustments[id] || {};
}

function renderExpertControls(h) {
  const id = h.id || "";
  const adj = adjustmentFor(id);
  const checked = adj.reject ? "checked" : "";
  return '<div class="expert-panel" data-hypothesis-id="' + escapeHtml(id) + '">' +
    '<div><b style="font-size:13px">Экспертная корректировка</b></div>' +
    '<div class="expert-controls">' +
      '<label>Риск<input class="expert-input" data-field="risk_adjustment" type="number" min="-1" max="1" step="0.05" value="' + escapeHtml(adj.risk_adjustment ?? "") + '"></label>' +
      '<label>Ценность<input class="expert-input" data-field="value_adjustment" type="number" min="-1" max="1" step="0.05" value="' + escapeHtml(adj.value_adjustment ?? "") + '"></label>' +
      '<label>Новизна<input class="expert-input" data-field="novelty_adjustment" type="number" min="-1" max="1" step="0.05" value="' + escapeHtml(adj.novelty_adjustment ?? "") + '"></label>' +
      '<label>Данные<input class="expert-input" data-field="evidence_strength_adjustment" type="number" min="-1" max="1" step="0.05" value="' + escapeHtml(adj.evidence_strength_adjustment ?? "") + '"></label>' +
    '</div>' +
    '<label style="display:grid;gap:4px;font-size:11px;color:#5f6368">Заметка<input class="expert-input" data-field="note" type="text" value="' + escapeHtml(adj.note ?? "") + '"></label>' +
    '<label style="display:grid;gap:4px;font-size:11px;color:#5f6368">Оценка 1-5<input class="feedback-input" data-field="rating" type="number" min="1" max="5" step="1" value="4"></label>' +
    '<label style="display:grid;gap:4px;font-size:11px;color:#5f6368">Комментарий<input class="feedback-input" data-field="comment" type="text" value=""></label>' +
    '<div class="expert-actions">' +
      '<label style="font-size:12px;color:#5f6368"><input class="expert-input" data-field="reject" type="checkbox" ' + checked + '> отклонить</label>' +
      '<button class="primary apply-expert" type="button">Пересчитать</button>' +
      '<button class="primary save-feedback" type="button">Сохранить feedback</button>' +
      '<button class="danger clear-expert" type="button">Сбросить</button>' +
    '</div>' +
  '</div>';
}

function renderHypotheses(data) {
  state.lastHypothesisResult = data;
  $("exportHypothesesJson").disabled = !data?.hypotheses?.length;
  $("exportHypothesesCsv").disabled = !data?.hypotheses?.length;
  $("exportHypothesesXlsx").disabled = !data?.hypotheses?.length;
  $("exportHypothesesDocx").disabled = !data?.hypotheses?.length;
  $("exportHypothesesPdf").disabled = !data?.hypotheses?.length;
  const warnings = (data.warnings||[]).map(r => '<span class="chip" style="border-color:#fdd835;background:#fffde7">' + escapeHtml(r) + "</span>").join("");
  const hypotheses = data.hypotheses || [];
  const cards = hypotheses.length ? hypotheses.map(h =>
    '<div class="answer-card">' +
      '<div class="hypothesis-meta"><span class="hypothesis-rank">#' + escapeHtml(h.rank || "") + '</span><span class="hypothesis-type">' + escapeHtml(hypothesisTypeLabel(h.hypothesis_type)) + '</span></div>' +
      '<h3>' + escapeHtml(h.statement || UI_TEXT.noHypotheses) + '</h3>' +
      renderScoreGrid(h.score) +
      '<div><b style="font-size:13px">Обоснование</b><p style="font-size:13px;line-height:1.5;color:#3c4043;margin-top:4px">' + escapeHtml(h.rationale || "") + '</p></div>' +
      '<div><b style="font-size:13px">План проверки</b><p style="font-size:13px;line-height:1.5;color:#3c4043;margin-top:4px">' + escapeHtml(h.test_plan || "") + '</p></div>' +
      '<div><b style="font-size:13px">Новизна</b><p style="font-size:13px;line-height:1.5;color:#3c4043;margin-top:4px">' + escapeHtml(h.novelty_rationale || "") + '</p></div>' +
      '<div><b style="font-size:13px">Риски</b>' + renderStringList(h.risk_items, "Риски не указаны") + '</div>' +
      '<div><b style="font-size:13px">Критерии фальсификации</b>' + renderStringList(h.falsification_criteria, "Критерии не указаны") + '</div>' +
      '<div><b style="font-size:13px">Что нужно собрать</b>' + renderStringList(h.required_evidence, "Нет списка evidence") + '</div>' +
      renderIdChips("Supporting entity IDs", h.supporting_entity_ids) +
      renderIdChips("Evidence IDs", h.supporting_evidence_ids) +
      renderIdChips("Observation IDs", h.supporting_observation_ids) +
      renderIdChips("Text unit IDs", h.supporting_text_unit_ids) +
      renderIdChips("Data gap IDs", h.data_gap_ids) +
      renderExpertControls(h) +
    '</div>'
  ).join("") : '<div class="answer-card"><h3>' + UI_TEXT.noHypotheses + '</h3><span style="font-size:13px;color:#5f6368">Уточните KPI или загрузите источники.</span></div>';
  addMsg("assistant",
    '<div class="bubble">Сформирован список гипотез для KPI: <b>' + escapeHtml(data.target_kpi || "") + "</b></div>" +
    (warnings ? '<div class="answer-card"><h3>Предупреждения</h3><div class="chips">' + warnings + "</div></div>" : "") +
    renderKnowledgeSummary(data) +
    renderAgentTrace(data.agent_trace || []) +
    cards
  );
}

async function runHypothesisJob(payload) {
  let job = await postJson(UI_CONFIG.endpoints.hypothesesGenerate, payload);
  addMsg("assistant", '<div class="bubble">Генерация гипотез запущена: ' + escapeHtml(job.job_id) + ".</div>");
  while (job.status === "queued" || job.status === "running") {
    if ($("generateHypotheses")) {
      $("generateHypotheses").textContent = job.message || "Генерация...";
    }
    await new Promise(resolve => setTimeout(resolve, 1200));
    const r = await fetch(UI_CONFIG.endpoints.hypothesesJobBase + encodeURIComponent(job.job_id));
    if (!r.ok) throw new Error(await r.text() || r.statusText);
    job = await r.json();
  }
  if (job.status === "failed") {
    throw new Error(job.error || "Hypothesis generation failed");
  }
  return job.result || {};
}

async function generateHypothesesFromKpi() {
  const targetKpi = $("targetKpi").value.trim();
  if (!targetKpi) {
    addMsg("assistant", '<div class="bubble error">' + UI_TEXT.hypothesisMissingKpi + "</div>");
    $("targetKpi").focus();
    return;
  }
  $("generateHypotheses").disabled = true;
  const oldButtonText = $("generateHypotheses").textContent;
  addMsg("user", '<div class="bubble">KPI: ' + escapeHtml(targetKpi) + "</div>");
  try {
    const sourceIds = getSelectedSources();
    const maxHypotheses = Math.max(1, Math.min(20, Number($("hypothesisLimit").value || 5)));
    const payload = {
      target_kpi: targetKpi,
      question: targetKpi,
      max_hypotheses: maxHypotheses
    };
    if (sourceIds) payload.source_ids = sourceIds;
    state.lastHypothesisRequest = payload;
    state.expertAdjustments = {};
    const data = await runHypothesisJob(payload);
    renderHypotheses(data);
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  } finally {
    $("generateHypotheses").disabled = false;
    $("generateHypotheses").textContent = oldButtonText;
  }
}

function updateExpertAdjustment(panel, input) {
  const id = panel?.dataset?.hypothesisId;
  const field = input?.dataset?.field;
  if (!id || !field) return;
  const next = { ...(state.expertAdjustments[id] || {}) };
  if (input.type === "checkbox") {
    if (input.checked) next[field] = true;
    else delete next[field];
  } else if (input.type === "number") {
    if (input.value === "") delete next[field];
    else next[field] = Number(input.value);
  } else if (input.value.trim()) {
    next[field] = input.value.trim();
  } else {
    delete next[field];
  }
  if (Object.keys(next).length) state.expertAdjustments[id] = next;
  else delete state.expertAdjustments[id];
}

async function applyExpertAdjustments() {
  if (!state.lastHypothesisRequest) return;
  const payload = {
    ...state.lastHypothesisRequest,
    expert_adjustments: state.expertAdjustments
  };
  addMsg("user", '<div class="bubble">Экспертные корректировки применены</div>');
  try {
    const data = await runHypothesisJob(payload);
    renderHypotheses(data);
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  }
}

function hypothesisById(id) {
  return (state.lastHypothesisResult?.hypotheses || []).find(h => h.id === id);
}

async function saveExpertFeedback(panel) {
  const id = panel?.dataset?.hypothesisId;
  const hypothesis = hypothesisById(id);
  if (!id || !hypothesis?.score) return;
  const ratingInput = panel.querySelector('.feedback-input[data-field="rating"]');
  const commentInput = panel.querySelector('.feedback-input[data-field="comment"]');
  const rejectInput = panel.querySelector('.expert-input[data-field="reject"]');
  const rating = rejectInput?.checked ? 1 : Math.max(1, Math.min(5, Number(ratingInput?.value || 4)));
  try {
    const data = await postJson(UI_CONFIG.endpoints.feedback, {
      hypothesis_id: id,
      rating,
      score: hypothesis.score,
      expert_id: "ui",
      comment: commentInput?.value || ""
    });
    addMsg("assistant", '<div class="bubble">Feedback сохранён. Записей: ' + escapeHtml(data.sample_size) + ".</div>");
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  }
}

async function exportHypotheses(format) {
  if (!state.lastHypothesisResult?.hypotheses?.length) return;
  try {
    const url = endpointWithParams(UI_CONFIG.endpoints.hypothesesExport, { format });
    await downloadFromPost(url, { result: state.lastHypothesisResult }, "materials-hypotheses." + format);
  } catch(e) {
    addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
  }
}
