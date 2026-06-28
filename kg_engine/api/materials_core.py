"""Thin REST API for the graph-first materials KG core."""

from __future__ import annotations

import csv
import io
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi import UploadFile
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from pydantic import BaseModel
from pydantic import Field

from kg_engine.domain.models import DocumentInput
from kg_engine.domain.models import ExperimentInput
from kg_engine.domain.models import PropertyFilters
from kg_engine.domain.models import QueryFilters
from kg_engine.domain.models import ReferenceDataBatch
from kg_engine.domain.models import RelationType
from kg_engine.ingestion.adapters import DocumentCorpusAdapter
from kg_engine.ingestion.adapters import ExperimentCatalogAdapter
from kg_engine.ingestion.adapters import ReferenceDataAdapter
from kg_engine.repositories.factory import create_materials_repository
from kg_engine.services.materials_kg import MaterialsKGService

if TYPE_CHECKING:
    from kg_engine.config.settings import Settings

_TEXT_SUFFIXES = {".txt", ".md"}
_STRUCTURED_SUFFIXES = {".json", ".jsonl", ".csv", ".tsv"}


def _parse_uploaded_file(name: str, content: bytes) -> object | None:
    suffix = Path(name).suffix.lower()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        return [dict(row) for row in reader]
    if suffix in _TEXT_SUFFIXES:
        title = Path(name).stem
        if suffix == ".md":
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip() or title
                    break
        return [{"document_id": name, "title": title, "text": text, "metadata": {"source_file": name}}]
    return None


class MaterialModeRequest(BaseModel):
    material: str = Field(min_length=1)
    mode: str | None = Field(default=None)
    property_name: str | None = Field(default=None)


class PropertyQueryRequest(BaseModel):
    property_name: str = Field(min_length=1)
    filters: PropertyFilters = Field(default_factory=PropertyFilters)


class RelatedQueryRequest(BaseModel):
    entity: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=5)
    relation_filters: list[str] = Field(default_factory=list)


class DecisionHistoryRequest(BaseModel):
    entity_or_experiment: str = Field(min_length=1)


class DataGapQueryRequest(BaseModel):
    scope: str | None = Field(default=None)
    filters: QueryFilters = Field(default_factory=QueryFilters)


class AnswerQueryRequest(BaseModel):
    question: str = Field(default="", max_length=4000)
    material: str | None = Field(default=None)
    mode: str | None = Field(default=None)
    property_name: str | None = Field(default=None)
    source_ids: list[str] | None = Field(default=None)


def _notebook_dashboard_html() -> str:
    return """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Materials KG</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      height: 100vh;
      background: #f0f2f5;
      color: #202124;
      font-family: "Google Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
      -webkit-font-smoothing: antialiased;
    }
    .app {
      height: 100vh;
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 0;
    }
    .sources {
      background: #fff;
      border-right: 1px solid #dadce0;
      display: grid;
      grid-template-rows: 48px auto 1fr;
      min-width: 0;
    }
    .sources-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px 0 20px;
      border-bottom: 1px solid #dadce0;
    }
    .sources-top span { font-size: 15px; font-weight: 500; }
    .sources-top button {
      width: 32px; height: 32px;
      border: none; background: none;
      border-radius: 50%;
      display: grid; place-items: center;
      color: #5f6368; font-size: 18px;
      cursor: pointer;
    }
    .sources-top button:hover { background: #f1f3f4; }
    .add-sources {
      margin: 16px 16px 0;
      height: 42px;
      border: 1px solid #dadce0;
      border-radius: 24px;
      background: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 500;
      color: #202124;
      cursor: pointer;
      transition: background 0.15s;
    }
    .add-sources:hover { background: #f1f3f4; }
    .add-sources .plus { font-size: 20px; color: #5f6368; }
    .source-list {
      padding: 8px 16px 16px;
      overflow: auto;
      display: grid;
      align-content: start;
      gap: 8px;
    }
    .source-empty {
      min-height: 300px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 24px 20px;
    }
    .source-empty .doc-icon {
      width: 36px; height: 36px;
      margin: 0 auto 14px;
      color: #9aa0a6;
    }
    .source-empty .doc-icon svg { width: 100%; height: 100%; fill: currentColor; }
    .source-empty strong {
      display: block;
      font-size: 14px;
      font-weight: 500;
      color: #5f6368;
      margin-bottom: 8px;
    }
    .source-empty p {
      font-size: 13px;
      color: #9aa0a6;
      line-height: 1.45;
      max-width: 260px;
      margin: 0 auto;
    }
    .source-row {
      display: grid;
      grid-template-columns: 36px 1fr auto;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid #e8eaed;
      border-radius: 10px;
      background: #fff;
    }
    .source-row:hover { background: #f8f9fa; }
    .source-icon {
      width: 36px; height: 36px;
      border-radius: 8px;
      display: grid; place-items: center;
      font-size: 11px; font-weight: 700;
      color: #fff;
    }
    .source-icon.json { background: #1a73e8; }
    .source-icon.jsonl { background: #1a73e8; }
    .source-icon.csv { background: #34a853; }
    .source-icon.tsv { background: #34a853; }
    .source-icon.txt { background: #9aa0a6; }
    .source-icon.md { background: #9334e6; }
    .source-icon.unknown { background: #5f6368; }
    .source-info b { display: block; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
    .source-info span { font-size: 11px; color: #9aa0a6; }
    .source-count {
      min-width: 28px; height: 22px;
      padding: 0 8px;
      border-radius: 11px;
      background: #e8f0fe;
      color: #1a73e8;
      font-size: 12px; font-weight: 600;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }
    .drop-overlay {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(26,115,232,0.08);
      border: 3px dashed #1a73e8;
      z-index: 100;
      place-items: center;
      font-size: 18px;
      color: #1a73e8;
      font-weight: 500;
    }
    .drop-overlay.active { display: grid; }
    .upload-progress {
      padding: 8px 16px;
      font-size: 12px;
      color: #5f6368;
      display: none;
    }
    .upload-progress.active { display: block; }
    .chat {
      display: grid;
      grid-template-rows: 48px 1fr auto;
      background: #fff;
      min-width: 0;
    }
    .chat-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px 0 20px;
      border-bottom: 1px solid #dadce0;
    }
    .chat-top span { font-size: 15px; font-weight: 500; }
    .chat-top button {
      width: 32px; height: 32px;
      border: none; background: none;
      border-radius: 50%;
      display: grid; place-items: center;
      color: #5f6368; font-size: 20px;
      cursor: pointer;
    }
    .chat-top button:hover { background: #f1f3f4; }
    .chat-body {
      overflow: auto;
      padding: 0;
      display: grid;
      align-content: start;
    }
    .hero {
      min-height: calc(100vh - 160px);
      display: grid;
      place-items: center;
      text-align: center;
      padding: 40px 20px;
    }
    .hero-inner { display: grid; gap: 8px; justify-items: center; }
    .hero-icon {
      width: 48px; height: 48px;
      border-radius: 10px;
      background: linear-gradient(135deg, #7c4dff 0%, #536dfe 100%);
      display: grid; place-items: center;
      color: #fff; font-size: 20px;
      box-shadow: 0 2px 8px rgba(124,77,255,0.3);
    }
    .hero h1 { margin: 16px 0 0; font-size: 24px; font-weight: 400; color: #202124; }
    .hero p { font-size: 13px; color: #9aa0a6; max-width: 340px; }
    .msg {
      max-width: 800px;
      width: 100%;
      margin: 0 auto;
      padding: 16px 20px;
      display: grid;
      gap: 8px;
    }
    .msg.user { justify-items: end; }
    .bubble {
      border: 1px solid #e8eaed;
      border-radius: 18px;
      padding: 12px 16px;
      font-size: 14px;
      line-height: 1.5;
      max-width: 700px;
    }
    .msg.user .bubble { background: #f1f3f4; }
    .msg.assistant .bubble { background: #fff; border-color: #dadce0; }
    .answer-card {
      border: 1px solid #e8eaed;
      border-radius: 14px;
      padding: 14px;
      background: #fff;
      display: grid;
      gap: 10px;
    }
    .answer-card h3 {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      color: #5f6368;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      height: 26px;
      padding: 0 10px;
      border-radius: 13px;
      border: 1px solid #e8eaed;
      background: #f1f3f4;
      font-size: 12px;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .chip .kind { color: #9aa0a6; }
    .mini-list { display: grid; gap: 6px; list-style: none; }
    .mini-list li {
      border: 1px solid #e8eaed;
      border-radius: 10px;
      padding: 8px 10px;
      background: #f8f9fa;
      display: grid;
      gap: 3px;
    }
    .mini-list b { font-size: 13px; font-weight: 500; }
    .mini-list span { font-size: 12px; color: #9aa0a6; }
    table.data { width: 100%; border-collapse: collapse; font-size: 13px; }
    table.data th, table.data td {
      padding: 7px 8px;
      border-bottom: 1px solid #e8eaed;
      text-align: left;
    }
    table.data th { color: #9aa0a6; font-size: 12px; font-weight: 500; background: #f8f9fa; }
    .error { color: #d93025; }
    .composer-wrap { padding: 8px 20px 20px; }
    .composer {
      border: 1px solid #dadce0;
      border-radius: 24px;
      background: #fff;
      display: grid;
      grid-template-columns: 1fr auto auto;
      align-items: end;
      gap: 8px;
      padding: 8px 8px 8px 18px;
      transition: border-color 0.15s;
    }
    .composer:focus-within { border-color: #1a73e8; }
    .composer textarea {
      width: 100%;
      min-height: 24px;
      max-height: 120px;
      border: none;
      outline: none;
      resize: none;
      font: inherit;
      font-size: 15px;
      line-height: 1.45;
      color: #202124;
      background: transparent;
      padding: 6px 0;
    }
    .composer textarea::placeholder { color: #9aa0a6; }
    .composer .src-label {
      font-size: 13px;
      color: #9aa0a6;
      white-space: nowrap;
      padding-bottom: 6px;
    }
    .send-btn {
      width: 40px; height: 40px;
      border-radius: 50%;
      border: none;
      background: #1a73e8;
      color: #fff;
      display: grid; place-items: center;
      font-size: 20px;
      cursor: pointer;
      flex-shrink: 0;
      margin-bottom: 2px;
    }
    .send-btn:hover { background: #1557b0; }
    .send-btn:disabled { background: #dadce0; cursor: default; }
    .send-btn svg { width: 20px; height: 20px; fill: #fff; }
    .source-check {
      position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
      width: 16px; height: 16px; accent-color: #1a73e8; cursor: pointer;
    }
    .source-row { position: relative; padding-left: 34px; }
    .citation {
      display: inline-block;
      background: #e8f0fe;
      color: #1a73e8;
      font-size: 11px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      cursor: pointer;
      margin: 0 2px;
      vertical-align: baseline;
    }
    .citation:hover { background: #d2e3fc; }
    .citations-block {
      border: 1px solid #e8eaed;
      border-radius: 10px;
      padding: 10px;
      background: #f8f9fa;
      display: grid;
      gap: 6px;
    }
    .citations-block h4 { margin: 0; font-size: 12px; color: #5f6368; text-transform: uppercase; }
    .cite-item {
      font-size: 12px; color: #5f6368; line-height: 1.4;
      padding: 4px 0; border-bottom: 1px solid #e8eaed;
    }
    .cite-item:last-child { border-bottom: 0; }
    .cite-item b { color: #202124; }
    .suggestions {
      display: flex; flex-wrap: wrap; gap: 6px;
      padding: 8px 20px;
    }
    .suggestion {
      height: 30px; padding: 0 12px;
      border: 1px solid #dadce0; border-radius: 15px;
      background: #fff; font-size: 12px; color: #5f6368;
      display: inline-flex; align-items: center;
      cursor: pointer; white-space: nowrap;
    }
    .suggestion:hover { background: #f1f3f4; border-color: #1a73e8; color: #1a73e8; }
    .overview-card {
      border: 1px solid #e8eaed; border-radius: 10px;
      padding: 10px; background: #f8f9fa;
      font-size: 13px; color: #5f6368; line-height: 1.45;
    }
    @media (max-width: 860px) {
      .app { grid-template-columns: 1fr; }
      .sources { display: none; }
    }
    .graph-toggle {
      width: 32px; height: 32px;
      border: none; background: none;
      border-radius: 50%;
      display: grid; place-items: center;
      color: #5f6368; font-size: 18px;
      cursor: pointer;
    }
    .graph-toggle:hover { background: #f1f3f4; }
    .graph-toggle svg { width: 20px; height: 20px; fill: currentColor; }
    .graph-panel {
      position: fixed; top: 0; right: 0;
      width: 400px; height: 100vh;
      background: #fff;
      box-shadow: -2px 0 12px rgba(0,0,0,0.1);
      z-index: 200;
      transform: translateX(100%);
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      display: grid;
      grid-template-rows: 48px 1fr;
    }
    .graph-panel.open { transform: translateX(0); }
    .graph-panel-top {
      display: flex; align-items: center;
      justify-content: space-between;
      padding: 0 12px 0 16px;
      border-bottom: 1px solid #dadce0;
    }
    .graph-panel-top span { font-size: 15px; font-weight: 500; }
    .graph-close {
      width: 32px; height: 32px;
      border: none; background: none;
      border-radius: 50%;
      display: grid; place-items: center;
      color: #5f6368; font-size: 18px;
      cursor: pointer;
    }
    .graph-close:hover { background: #f1f3f4; }
    .graph-body {
      overflow: auto; padding: 12px;
      display: grid; gap: 12px;
      align-content: start;
    }
    .graph-legend {
      display: flex; flex-wrap: wrap; gap: 6px;
      padding-bottom: 8px;
      border-bottom: 1px solid #e8eaed;
    }
    .legend-item {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 11px; color: #5f6368;
    }
    .legend-dot {
      width: 10px; height: 10px;
      border-radius: 3px;
    }
    .graph-svg-wrap {
      border: 1px solid #e8eaed;
      border-radius: 10px;
      background: #f8f9fa;
      overflow: auto;
      min-height: 300px;
    }
    .graph-svg-wrap svg {
      display: block;
    }
    .graph-stats {
      font-size: 12px; color: #9aa0a6;
      text-align: center;
    }
    .graph-node-rect {
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .graph-node-rect:hover { opacity: 0.8; }
    .graph-edge { transition: opacity 0.2s; }
    .graph-edge.dimmed { opacity: 0.1; }
    .graph-node-rect.dimmed { opacity: 0.25; }
    .graph-tooltip {
      position: fixed;
      background: #202124;
      color: #fff;
      font-size: 12px;
      padding: 4px 8px;
      border-radius: 4px;
      pointer-events: none;
      z-index: 300;
      display: none;
      white-space: nowrap;
    }
    @media (max-width: 860px) {
      .graph-panel { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="drop-overlay" id="dropOverlay">Перетащите файлы сюда</div>
  <input type="file" id="fileInput" multiple accept=".json,.jsonl,.csv,.tsv,.txt,.md" style="display:none">
  <div class="app">
    <aside class="sources">
      <div class="sources-top">
        <span>Источники</span>
        <button title="Свернуть">&#9634;</button>
      </div>
      <button class="add-sources" id="addSources">
        <span class="plus">+</span> Добавить источники
      </button>
      <div class="upload-progress" id="uploadProgress">Загрузка файлов...</div>
      <div class="source-list" id="sources">
        <div class="source-empty" id="sourceEmpty">
          <div>
            <div class="doc-icon">
              <svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
            </div>
            <strong>Здесь появятся загруженные источники</strong>
            <p>Нажмите &laquo;Добавить источник&raquo; или перетащите файлы: JSON, JSONL, CSV, TSV, TXT, MD</p>
          </div>
        </div>
      </div>
    </aside>
    <section class="chat">
      <div class="chat-top">
        <span>Чат</span>
        <div style="display:flex;gap:4px;align-items:center">
          <button class="graph-toggle" id="graphToggle" title="Граф знаний">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
          </button>
          <button title="Меню">&vellip;</button>
        </div>
      </div>
      <main class="chat-body" id="chatBody">
        <div class="hero" id="hero">
          <div class="hero-inner">
            <div class="hero-icon">&#128218;</div>
            <h1>Блокнот материалов</h1>
            <p id="notebookMeta">0 источников</p>
          </div>
        </div>
        <div class="suggestions" id="suggestions"></div>
      </main>
      <div class="composer-wrap">
        <div class="composer">
          <textarea id="question" rows="1" placeholder="Введите текст..." aria-label="Исследовательский вопрос"></textarea>
          <span class="src-label" id="sourceNote">0 источников</span>
          <button class="send-btn" id="sendQuestion" title="Отправить">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
      </div>
    </section>
  </div>
  <div class="graph-tooltip" id="graphTooltip"></div>
  <div class="graph-panel" id="graphPanel">
    <div class="graph-panel-top">
      <span>Граф знаний</span>
      <button class="graph-close" id="graphClose" title="Закрыть">&times;</button>
    </div>
    <div class="graph-body">
      <div class="graph-legend" id="graphLegend"></div>
      <div class="graph-svg-wrap" id="graphSvgWrap"></div>
      <div class="graph-stats" id="graphStats"></div>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const state = { files: [], total: 0 };

    function escapeHtml(v) {
      return String(v ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    }
    async function postJson(url, payload = {}) {
      const r = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      return r.json();
    }
    function formatSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / 1048576).toFixed(1) + " MB";
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
      if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">Нет данных</span>';
      return '<div class="chips">' + rows.slice(0,20).map(r =>
        '<span class="chip">' + escapeHtml(r.canonical_name) + ' <span class="kind">' + escapeHtml(r.kind) + "</span></span>"
      ).join("") + "</div>";
    }
    function listBlock(rows, render, empty) {
      if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">' + escapeHtml(empty) + "</span>";
      return '<ul class="mini-list">' + rows.slice(0,8).map(r => "<li>" + render(r) + "</li>").join("") + "</ul>";
    }
    function tableBlock(rows) {
      if (!rows?.length) return '<span style="color:#9aa0a6;font-size:13px">Измерения не найдены</span>';
      return '<table class="data"><thead><tr><th>Значение</th><th>Единица</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>' +
        rows.slice(0,10).map(r => "<tr><td>" + escapeHtml(r.value??"n/a") + "</td><td>" + escapeHtml(r.unit??"") + "</td><td>" + escapeHtml(r.confidence) + "</td><td>" + escapeHtml(r.evidence_id) + "</td></tr>").join("") +
        "</tbody></table>";
    }
    function renderCitations(citations) {
      if (!citations?.length) return "";
      const items = citations.slice(0,8).map(c =>
        '<div class="cite-item"><b>[' + escapeHtml(c.source_kind) + '] ' + escapeHtml(c.source_id) + "</b> — " + escapeHtml((c.fragment||"").substring(0,150)) + (c.fragment?.length > 150 ? "..." : "") + "</div>"
      ).join("");
      return '<div class="citations-block"><h3>Источники цитат</h3>' + items + "</div>";
    }
    function getSelectedSources() {
      const checks = document.querySelectorAll('.source-check:checked');
      if (!checks.length) return null;
      return Array.from(checks).map(c => c.dataset.name).filter(Boolean);
    }
    function renderSources(uploadResult) {
      const uploaded = uploadResult.uploaded || [];
      uploaded.forEach(f => {
        if (!state.files.find(x => x.name === f.name)) state.files.push(f);
      });
      state.total = state.files.length;
      $("sourceNote").textContent = state.total + " источников";
      $("notebookMeta").textContent = state.total + " источников";
      $("sourceEmpty")?.remove();
      $("sources").innerHTML = state.files.map(f => {
        const t = f.type || "unknown";
        return '<div class="source-row"><input type="checkbox" class="source-check" checked data-name="' + escapeHtml(f.name) + '">' +
          '<div class="source-icon ' + t + '">' + t.toUpperCase() + "</div>" +
          '<div class="source-info"><b>' + escapeHtml(f.name) + "</b><span>" + formatSize(f.size) + "</span></div></div>";
      }).join("");
      if (uploadResult.overview) {
        const ov = uploadResult.overview;
        addMsg("assistant", '<div class="overview-card">' + escapeHtml(ov.summary) + "</div>");
      }
      if (uploadResult.suggested_questions?.length) {
        renderSuggestions(uploadResult.suggested_questions);
      }
    }
    function renderSuggestions(questions) {
      $("suggestions").innerHTML = questions.map(q =>
        '<button class="suggestion" type="button">' + escapeHtml(q) + "</button>"
      ).join("");
      document.querySelectorAll(".suggestion").forEach(btn => {
        btn.addEventListener("click", () => {
          $("question").value = btn.textContent;
          ask();
        });
      });
    }
    function renderAnswer(data) {
      const w = (data.warnings||[]).map(r => '<span class="chip" style="border-color:#fdd835;background:#fffde7">' + escapeHtml(r) + "</span>").join("");
      const citations = renderCitations(data.citations);
      addMsg("assistant",
        '<div class="bubble">' + escapeHtml(data.answer||"Ответ не сформирован.") + "</div>" +
        (w ? '<div class="answer-card"><h3>Предупреждения</h3><div class="chips">' + w + "</div></div>" : "") +
        '<div class="answer-card"><h3>Найденные сущности</h3>' + chipList(data.matched_entities) + "</div>" +
        '<div class="answer-card"><h3>Что уже делали</h3>' + listBlock(data.experiments, r => "<b>" + escapeHtml(r.canonical_name) + "</b><span>" + escapeHtml(r.id) + "</span>", "Эксперименты не найдены") + "</div>" +
        '<div class="answer-card"><h3>Эффект и измерения</h3>' + tableBlock(data.observations) + "</div>" +
        (citations ? '<div class="answer-card">' + citations + "</div>" : "") +
        '<div class="answer-card"><h3>Связанные сущности</h3>' + chipList(data.related_entities) + "</div>" +
        '<div class="answer-card"><h3>История решений</h3>' + listBlock(data.decision_history, r => "<b>" + escapeHtml(r.summary) + "</b><span>" + escapeHtml(r.decision||"вывод") + "</span>", "История решений не найдена") + "</div>" +
        '<div class="answer-card"><h3>Пробелы данных</h3>' + listBlock(data.data_gaps, r => "<b>" + escapeHtml(r.reason) + "</b><span>" + escapeHtml(r.scope) + "</span>", "Пробелы не найдены") + "</div>"
      );
    }
    async function uploadFiles(files) {
      if (!files.length) return;
      $("uploadProgress").classList.add("active");
      $("addSources").disabled = true;
      try {
        const fd = new FormData();
        for (const f of files) fd.append("files", f);
        const r = await fetch("/ingest/upload", { method: "POST", body: fd });
        if (!r.ok) throw new Error(await r.text() || r.statusText);
        const data = await r.json();
        renderSources(data);
        const counts = [];
        if (data.reference?.entities) counts.push(data.reference.entities + " сущностей");
        if (data.experiments?.experiments) counts.push(data.experiments.experiments + " экспериментов");
        if (data.documents?.documents) counts.push(data.documents.documents + " документов");
        addMsg("assistant", '<div class="bubble">Загружено: ' + (counts.join(", ") || "файлы приняты") + ". Задавайте вопросы.</div>');
      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      } finally {
        $("uploadProgress").classList.remove("active");
        $("addSources").disabled = false;
      }
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
        const data = await postJson("/query/answer", payload);
        renderAnswer(data);
        if (data.citations?.length) {
          const suggestions = await fetch("/source/suggestions").then(r => r.json()).catch(() => []);
          if (suggestions.length) renderSuggestions(suggestions);
        }
      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      } finally {
        $("sendQuestion").disabled = false;
      }
    }
    $("addSources").addEventListener("click", () => $("fileInput").click());
    $("fileInput").addEventListener("change", e => { uploadFiles(Array.from(e.target.files)); e.target.value = ""; });
    $("sendQuestion").addEventListener("click", ask);
    $("question").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
    $("question").addEventListener("input", function() { this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 120) + "px"; });
    let dragTimer;
    document.addEventListener("dragenter", e => { e.preventDefault(); clearTimeout(dragTimer); $("dropOverlay").classList.add("active"); });
    document.addEventListener("dragover", e => e.preventDefault());
    document.addEventListener("dragleave", e => { e.preventDefault(); dragTimer = setTimeout(() => $("dropOverlay").classList.remove("active"), 200); });
    document.addEventListener("drop", e => { e.preventDefault(); $("dropOverlay").classList.remove("active"); if (e.dataTransfer.files.length) uploadFiles(Array.from(e.dataTransfer.files)); });
    const KIND_COLORS = {
      material: "#1a73e8", property: "#34a853", mode: "#f9ab00",
      experiment: "#ea4335", equipment: "#9aa0a6", team: "#9334e6",
      document: "#fbbc04", tag: "#00897b"
    };
    const KIND_LABELS = {
      material: "Материал", property: "Свойство", mode: "Режим",
      experiment: "Эксперимент", equipment: "Оборудование", team: "Команда",
      document: "Документ", tag: "Тег"
    };
    const EDGE_COLORS = {
      evaluates_material: "#1a73e8", uses_mode: "#f9ab00",
      measures_property: "#34a853", uses_equipment: "#9aa0a6",
      performed_by: "#9334e6", documented_in: "#fbbc04",
      tagged_with: "#00897b", references: "#607d8b", related_to: "#455a64"
    };
    let graphData = null;
    let selectedNodeId = null;
    function buildLegend() {
      $("graphLegend").innerHTML = Object.keys(KIND_COLORS).map(k =>
        '<span class="legend-item"><span class="legend-dot" style="background:' + KIND_COLORS[k] + '"></span>' + (KIND_LABELS[k]||k) + '</span>'
      ).join("");
    }
    async function loadGraph() {
      if (graphData) { renderGraph(); return; }
      $("graphStats").textContent = "Загрузка...";
      try {
        const resp = await fetch("/graph/data");
        if (!resp.ok) throw new Error(resp.statusText);
        graphData = await resp.json();
        renderGraph();
      } catch(e) {
        $("graphStats").textContent = "Ошибка: " + e.message;
        $("graphSvgWrap").innerHTML = "";
      }
    }
    function renderGraph() {
      const nodes = graphData.nodes || [];
      const edges = graphData.edges || [];
      if (!nodes.length) {
        $("graphSvgWrap").innerHTML = '<div style="padding:24px;text-align:center;color:#9aa0a6;font-size:13px">Нет данных для отображения</div>';
        $("graphStats").textContent = "0 узлов, 0 связей";
        return;
      }
      const kindBuckets = {};
      nodes.forEach(n => { (kindBuckets[n.kind] = kindBuckets[n.kind] || []).push(n); });
      const kindOrder = Object.keys(KIND_COLORS);
      const presentKinds = kindOrder.filter(k => kindBuckets[k]);
      const colW = 130, rowH = 32, gap = 8, padX = 16, padY = 16;
      let maxColH = 0;
      presentKinds.forEach(k => {
        const h = kindBuckets[k].length * (rowH + gap);
        if (h > maxColH) maxColH = h;
      });
      maxColH = Math.max(maxColH, rowH);
      const svgW = presentKinds.length * colW + padX * 2;
      const svgH = maxColH + padY * 2 + 28;
      const nodePos = {};
      presentKinds.forEach((kind, ci) => {
        const col = kindBuckets[kind];
        col.forEach((n, ri) => {
          const x = padX + ci * colW;
          const y = padY + 28 + ri * (rowH + gap);
          nodePos[n.id] = { x, y, kind };
        });
      });
      let svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + svgW + '" height="' + svgH + '" style="font-family:system-ui,sans-serif">';
      svg += '<defs>';
      presentKinds.forEach(k => {
        svg += '<marker id="arrow-' + k + '" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto"><path d="M0,0 L6,2 L0,4" fill="#9aa0a6" opacity="0.5"/></marker>';
      });
      svg += '</defs>';
      presentKinds.forEach((kind, ci) => {
        const x = padX + ci * colW + 4;
        svg += '<text x="' + x + '" y="' + (padY + 16) + '" font-size="11" font-weight="600" fill="' + KIND_COLORS[kind] + '">' + (KIND_LABELS[kind] || kind) + '</text>';
      });
      const connectedIds = new Set();
      edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target); });
      edges.forEach(e => {
        const s = nodePos[e.source], t = nodePos[e.target];
        if (!s || !t) return;
        const sx = s.x + 4, sy = s.y + rowH / 2;
        const tx = t.x + 4, ty = t.y + rowH / 2;
        const edgeKind = (s.kind < t.kind) ? s.kind : t.kind;
        const color = EDGE_COLORS[e.type] || "#9aa0a6";
        svg += '<line class="graph-edge" data-source="' + e.source + '" data-target="' + e.target + '" x1="' + sx + '" y1="' + sy + '" x2="' + tx + '" y2="' + ty + '" stroke="' + color + '" stroke-width="1" opacity="0.35" marker-end="url(#arrow-' + edgeKind + ')"/>';
      });
      nodes.forEach(n => {
        const p = nodePos[n.id];
        if (!p) return;
        const color = KIND_COLORS[n.kind] || "#5f6368";
        const label = n.name.length > 14 ? n.name.substring(0, 12) + "..." : n.name;
        const isConn = connectedIds.has(n.id);
        svg += '<g class="graph-node-rect" data-id="' + n.id + '" data-name="' + escapeHtml(n.name) + '" data-kind="' + n.kind + '">';
        svg += '<rect x="' + p.x + '" y="' + p.y + '" width="120" height="' + rowH + '" rx="6" fill="#fff" stroke="' + color + '" stroke-width="1.5"/>';
        svg += '<rect x="' + p.x + '" y="' + p.y + '" width="4" height="' + rowH + '" rx="2" fill="' + color + '"/>';
        svg += '<text x="' + (p.x + 10) + '" y="' + (p.y + rowH / 2 + 4) + '" font-size="11" fill="#202124" font-weight="' + (isConn ? "600" : "400") + '">' + escapeHtml(label) + '</text>';
        svg += '</g>';
      });
      svg += '</svg>';
      $("graphSvgWrap").innerHTML = svg;
      $("graphStats").textContent = nodes.length + " узлов, " + edges.length + " связей";
      attachGraphEvents();
    }
    function attachGraphEvents() {
      const tooltip = $("graphTooltip");
      document.querySelectorAll(".graph-node-rect").forEach(g => {
        g.addEventListener("mouseenter", e => {
          tooltip.style.display = "block";
          tooltip.textContent = g.dataset.name + " (" + (KIND_LABELS[g.dataset.kind] || g.dataset.kind) + ")";
        });
        g.addEventListener("mousemove", e => {
          tooltip.style.left = (e.clientX + 12) + "px";
          tooltip.style.top = (e.clientY - 8) + "px";
        });
        g.addEventListener("mouseleave", () => { tooltip.style.display = "none"; });
        g.addEventListener("click", () => {
          const clickedId = g.dataset.id;
          if (selectedNodeId === clickedId) {
            selectedNodeId = null;
            document.querySelectorAll(".graph-node-rect").forEach(n => n.classList.remove("dimmed"));
            document.querySelectorAll(".graph-edge").forEach(e => e.classList.remove("dimmed"));
            return;
          }
          selectedNodeId = clickedId;
          const neighbors = new Set([clickedId]);
          document.querySelectorAll(".graph-edge").forEach(e => {
            if (e.dataset.source === clickedId || e.dataset.target === clickedId) {
              neighbors.add(e.dataset.source);
              neighbors.add(e.dataset.target);
              e.classList.remove("dimmed");
            } else {
              e.classList.add("dimmed");
            }
          });
          document.querySelectorAll(".graph-node-rect").forEach(n => {
            if (neighbors.has(n.dataset.id)) n.classList.remove("dimmed");
            else n.classList.add("dimmed");
          });
        });
      });
    }
    $("graphToggle").addEventListener("click", () => {
      $("graphPanel").classList.toggle("open");
      if ($("graphPanel").classList.contains("open")) {
        buildLegend();
        loadGraph();
      }
    });
    $("graphClose").addEventListener("click", () => { $("graphPanel").classList.remove("open"); });
  </script>
</body>
</html>
"""


def _create_llm_provider():
    """Create LLM provider if API key is configured, else None."""
    try:
        from kg_engine.llm_core.provider import create_provider_from_env
        return create_provider_from_env()
    except Exception:
        return None


def create_materials_app(
    *,
    settings: Settings | None = None,
    service: MaterialsKGService | None = None,
    ensure_schema: bool = False,
    title: str | None = None,
) -> FastAPI:
    """Create a standalone FastAPI app for the materials KG core."""
    api_title = title
    if settings is None:
        if service is None:
            from kg_engine.config.settings import settings as app_settings

            runtime_settings = app_settings
            if api_title is None:
                api_title = runtime_settings.materials_api_title
        else:
            runtime_settings = None
            if api_title is None:
                api_title = "Materials KG Core API"
    else:
        runtime_settings = settings
        if api_title is None:
            api_title = runtime_settings.materials_api_title
    runtime_service = service or MaterialsKGService(
        create_materials_repository(runtime_settings, ensure_schema=ensure_schema),
        llm_provider=_create_llm_provider(),
    )
    app = FastAPI(title=api_title)

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> Response:
        html = _notebook_dashboard_html()
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "materials-kg-core"}

    @app.get("/graph/data")
    def graph_data() -> dict:
        entities = runtime_service._repository.find_entities()  # noqa: SLF001
        relations = runtime_service._repository.list_relations()  # noqa: SLF001
        return {
            "nodes": [
                {
                    "id": e.id,
                    "kind": e.kind.value,
                    "name": e.canonical_name,
                }
                for e in entities
            ],
            "edges": [
                {
                    "id": r.id,
                    "type": r.relation_type.value,
                    "source": r.source_entity_id,
                    "target": r.target_entity_id,
                }
                for r in relations
            ],
        }

    @app.post("/ingest/upload")
    async def ingest_upload(files: list[UploadFile]) -> dict:
        ref_payload: dict = {}
        exp_payload: list = []
        doc_payload: list = []
        uploaded: list[dict] = []
        for upload in files:
            name = upload.filename or "unnamed"
            content = await upload.read()
            parsed = _parse_uploaded_file(name, content)
            suffix = Path(name).suffix.lower()
            uploaded.append({"name": name, "size": len(content), "type": suffix.lstrip(".") or "unknown"})
            if parsed is None:
                doc_payload.append({"document_id": name, "title": Path(name).stem, "text": content.decode("utf-8", errors="replace"), "metadata": {"source_file": name}})
                continue
            if suffix in _TEXT_SUFFIXES:
                if isinstance(parsed, list):
                    doc_payload.extend(parsed)
                else:
                    doc_payload.append(parsed)
                continue
            if isinstance(parsed, dict):
                for key in ("entities", "materials", "equipment", "properties", "modes", "teams", "documents", "tags", "coverage_rules"):
                    if key in parsed and isinstance(parsed[key], list):
                        ref_payload.setdefault(key, []).extend(parsed[key])
                if "experiments" in parsed and isinstance(parsed["experiments"], list):
                    exp_payload.extend(parsed["experiments"])
                if "documents" in parsed and isinstance(parsed["documents"], list):
                    doc_payload.extend(parsed["documents"])
                if not any(k in parsed for k in ("entities", "materials", "experiments", "documents")):
                    if parsed.get("kind") or parsed.get("entity_kind") or parsed.get("type"):
                        ref_payload.setdefault("entities", []).append(parsed)
                    else:
                        doc_payload.append({"document_id": name, "title": Path(name).stem, "text": json.dumps(parsed, ensure_ascii=False), "metadata": {"source_file": name}})
            elif isinstance(parsed, list):
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    if item.get("kind") or item.get("entity_kind") or item.get("type"):
                        ref_payload.setdefault("entities", []).append(item)
                    elif (item.get("experiment_id") or item.get("id")) and (item.get("material_name") or item.get("material")):
                        exp_payload.append(item)
                    elif item.get("document_id") or item.get("text") or item.get("content"):
                        doc_payload.append(item)
                    else:
                        doc_payload.append({"document_id": f"{name}#{parsed.index(item)}", "title": f"{Path(name).stem} #{parsed.index(item)}", "text": json.dumps(item, ensure_ascii=False), "metadata": {"source_file": name}})
        results = {}
        if ref_payload:
            results["reference"] = runtime_service.ingest_reference_data(ReferenceDataAdapter().from_payload(ref_payload))
        if exp_payload:
            results["experiments"] = runtime_service.ingest_experiments(ExperimentCatalogAdapter().from_payload(exp_payload))
        if doc_payload:
            results["documents"] = runtime_service.ingest_documents(DocumentCorpusAdapter().from_payload(doc_payload))
        results["uploaded"] = uploaded
        results["overview"] = runtime_service.get_source_overview()
        results["suggested_questions"] = runtime_service.get_suggested_questions()
        return results

    @app.post("/ingest/reference")
    def ingest_reference(batch: ReferenceDataBatch) -> dict[str, int]:
        return runtime_service.ingest_reference_data(batch)

    @app.post("/ingest/experiments")
    def ingest_experiments(batch: list[ExperimentInput]) -> dict[str, int]:
        return runtime_service.ingest_experiments(batch)

    @app.post("/ingest/documents")
    def ingest_documents(batch: list[DocumentInput]) -> dict[str, int]:
        return runtime_service.ingest_documents(batch)

    @app.post("/query/answer")
    def query_answer(request: AnswerQueryRequest) -> dict:
        return runtime_service.answer_question(
            question=request.question,
            material=request.material,
            mode=request.mode,
            property_name=request.property_name,
            source_ids=request.source_ids,
        )

    @app.get("/source/overview")
    def source_overview() -> dict:
        return runtime_service.get_source_overview()

    @app.get("/source/suggestions")
    def source_suggestions() -> list[str]:
        return runtime_service.get_suggested_questions()

    @app.post("/query/material-mode")
    def query_material_mode(request: MaterialModeRequest) -> dict:
        return runtime_service.query_material_mode(
            request.material,
            request.mode,
            request.property_name,
        ).model_dump(mode="json")

    @app.post("/query/property")
    def query_property(request: PropertyQueryRequest) -> dict:
        return runtime_service.query_property(
            request.property_name,
            request.filters,
        ).model_dump(mode="json")

    @app.post("/query/related")
    def query_related(request: RelatedQueryRequest) -> dict:
        relation_filters = (
            [RelationType(item) for item in request.relation_filters]
            if request.relation_filters
            else None
        )
        return runtime_service.query_related(
            request.entity,
            request.depth,
            relation_filters=relation_filters,
        ).model_dump(mode="json")

    @app.post("/query/decision-history")
    def query_decision_history(request: DecisionHistoryRequest) -> dict:
        return runtime_service.query_decision_history(
            request.entity_or_experiment
        ).model_dump(mode="json")

    @app.post("/query/data-gaps")
    def query_data_gaps(request: DataGapQueryRequest) -> list[dict]:
        return [
            gap.model_dump(mode="json")
            for gap in runtime_service.query_data_gaps(request.scope, request.filters)
        ]

    return app

