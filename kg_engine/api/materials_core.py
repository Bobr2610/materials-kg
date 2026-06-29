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
from kg_engine.domain.models import HypothesisInput
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
_SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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
        return [
            {
                "document_id": name,
                "title": title,
                "text": text,
                "metadata": {"source_file": name},
            }
        ]
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
    session_id: str | None = Field(default=None)


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
    html { height: 100%; }
    body {
      height: 100vh;
      background: #f0f2f5;
      color: #202124;
      font-family: "Google Sans", "Segoe UI", system-ui, -apple-system, sans-serif;
      -webkit-font-smoothing: antialiased;
      overflow: hidden;
    }
    .app {
      height: 100vh;
      display: grid;
      grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
      gap: 0;
      min-width: 0;
    }
    .app.sources-collapsed { grid-template-columns: 0 1fr; }
    .app.sources-collapsed .sources {
      overflow: hidden;
      border-right: 0;
      min-width: 0;
    }
    .sources {
      background: #fff;
      border-right: 1px solid #dadce0;
      display: grid;
      grid-template-rows: 48px auto auto auto minmax(0, 1fr);
      min-width: 0;
      min-height: 0;
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
      min-width: 0;
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
      white-space: nowrap;
    }
    .add-sources:hover { background: #f1f3f4; }
    .add-sources .plus { font-size: 20px; color: #5f6368; }
    .source-tools {
      padding: 10px 16px 6px;
      display: grid;
      gap: 8px;
      border-bottom: 1px solid #f1f3f4;
    }
    .source-search {
      height: 34px;
      border: 1px solid #dadce0;
      border-radius: 8px;
      padding: 0 10px;
      font: inherit;
      font-size: 13px;
      color: #202124;
      background: #fff;
      outline: none;
    }
    .source-search:focus { border-color: #1a73e8; }
    .source-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-height: 28px;
      min-width: 0;
    }
    .source-actions-group {
      display: flex;
      gap: 4px;
      align-items: center;
      min-width: 0;
    }
    .source-action {
      height: 28px;
      border: 1px solid #dadce0;
      border-radius: 7px;
      background: #fff;
      padding: 0 8px;
      font: inherit;
      font-size: 12px;
      color: #5f6368;
      cursor: pointer;
      white-space: nowrap;
    }
    .source-action:hover { background: #f8f9fa; color: #202124; }
    .source-summary {
      font-size: 11px;
      color: #9aa0a6;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      text-align: right;
    }
    .source-list {
      padding: 8px 16px 16px;
      overflow: auto;
      display: grid;
      align-content: start;
      grid-auto-rows: min-content;
      gap: 8px;
      min-height: 0;
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
      grid-template-columns: 18px 36px minmax(0, 1fr) 28px;
      align-items: center;
      gap: 10px;
      min-height: 54px;
      padding: 8px 8px;
      border: 1px solid #e8eaed;
      border-radius: 10px;
      background: #fff;
      min-width: 0;
    }
    .source-row:hover { background: #f8f9fa; }
    .source-row.is-muted { opacity: 0.56; }
    .source-icon {
      width: 36px; height: 36px;
      border-radius: 8px;
      display: grid; place-items: center;
      font-size: 11px; font-weight: 700;
      color: #fff;
      overflow: hidden;
    }
    .source-icon.json { background: #1a73e8; }
    .source-icon.jsonl { background: #1a73e8; }
    .source-icon.csv { background: #34a853; }
    .source-icon.tsv { background: #34a853; }
    .source-icon.txt { background: #9aa0a6; }
    .source-icon.md { background: #9334e6; }
    .source-icon.unknown { background: #5f6368; }
    .source-info { min-width: 0; }
    .source-info b { display: block; font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
      margin: 8px 16px 0;
      padding: 10px 12px;
      font-size: 12px;
      color: #5f6368;
      display: none;
      border: 1px solid #e8eaed;
      border-radius: 10px;
      background: #f8f9fa;
      gap: 8px;
      min-width: 0;
    }
    .upload-progress.active { display: grid; }
    .upload-progress-bar {
      height: 6px;
      border-radius: 999px;
      background: #e8eaed;
      overflow: hidden;
    }
    .upload-progress-fill {
      height: 100%;
      width: 0%;
      background: #1a73e8;
      transition: width 0.18s ease-out;
    }
    .source-more {
      height: 34px;
      border: 1px solid #dadce0;
      border-radius: 8px;
      background: #fff;
      color: #1a73e8;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    .source-more:hover { background: #f8f9fa; }
    .chat {
      display: grid;
      grid-template-rows: 48px 1fr auto;
      background: #fff;
      min-width: 0;
      min-height: 0;
    }
    .chat-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 12px 0 20px;
      border-bottom: 1px solid #dadce0;
      min-width: 0;
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
    .top-actions { position: relative; display: flex; gap: 4px; align-items: center; min-width: 0; }
    .restore-sources {
      display: none;
      width: auto !important;
      padding: 0 10px !important;
      border: 1px solid #dadce0 !important;
      border-radius: 16px !important;
      font-size: 13px !important;
      gap: 6px;
    }
    .app.sources-collapsed .restore-sources { display: inline-flex; }
    .menu-popover {
      display: none;
      position: absolute;
      top: 38px;
      right: 0;
      min-width: 190px;
      padding: 6px;
      border: 1px solid #dadce0;
      border-radius: 10px;
      background: #fff;
      box-shadow: 0 8px 24px rgba(60,64,67,0.18);
      z-index: 20;
    }
    .menu-popover.open { display: grid; }
    .menu-popover button {
      width: 100% !important;
      height: 34px !important;
      border-radius: 8px !important;
      display: flex !important;
      justify-content: flex-start;
      padding: 0 10px !important;
      font-size: 13px !important;
      color: #202124 !important;
    }
    .chat-body {
      overflow: auto;
      padding: 0;
      display: grid;
      align-content: start;
      min-height: 0;
      min-width: 0;
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
      min-width: 0;
    }
    .msg.user { justify-items: end; }
    .bubble {
      border: 1px solid #e8eaed;
      border-radius: 18px;
      padding: 12px 16px;
      font-size: 14px;
      line-height: 1.5;
      max-width: 700px;
      min-width: 0;
      overflow-wrap: anywhere;
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
      min-width: 0;
    }
    .answer-card h3 {
      margin: 0;
      font-size: 13px;
      font-weight: 600;
      color: #5f6368;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
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
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
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
    table.data { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
    table.data th, table.data td {
      padding: 7px 8px;
      border-bottom: 1px solid #e8eaed;
      text-align: left;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    table.data th { color: #9aa0a6; font-size: 12px; font-weight: 500; background: #f8f9fa; }
    .error { color: #d93025; }
    .composer-wrap { padding: 8px 20px 20px; }
    .composer {
      border: 1px solid #dadce0;
      border-radius: 24px;
      background: #fff;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto 40px;
      align-items: end;
      gap: 8px;
      padding: 8px 8px 8px 18px;
      transition: border-color 0.15s;
      min-width: 0;
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
      max-width: 160px;
      overflow: hidden;
      text-overflow: ellipsis;
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
      width: 16px; height: 16px; accent-color: #1a73e8; cursor: pointer;
    }
    .source-delete {
      width: 24px; height: 24px; border: none; background: none;
      border-radius: 50%; font-size: 16px; color: #9aa0a6; cursor: pointer;
      display: grid; place-items: center;
    }
    .source-delete:hover { background: #fce8e6; color: #d93025; }
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
      min-width: 0;
    }
    .suggestion {
      height: 30px; padding: 0 12px;
      border: 1px solid #dadce0; border-radius: 15px;
      background: #fff; font-size: 12px; color: #5f6368;
      display: inline-flex; align-items: center;
      cursor: pointer; white-space: nowrap;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .suggestion:hover { background: #f1f3f4; border-color: #1a73e8; color: #1a73e8; }
    .overview-card {
      border: 1px solid #e8eaed; border-radius: 10px;
      padding: 10px; background: #f8f9fa;
      font-size: 13px; color: #5f6368; line-height: 1.45;
      overflow-wrap: anywhere;
    }
    @media (max-width: 860px) {
      .app { grid-template-columns: 1fr; }
      .sources { display: none; }
      .app.sources-collapsed { grid-template-columns: 1fr; }
      .restore-sources { display: none !important; }
      .chat-top { padding-left: 14px; }
      .msg { padding: 12px 14px; }
      .composer-wrap { padding: 8px 12px 14px; }
      .composer {
        grid-template-columns: minmax(0, 1fr) 40px;
        border-radius: 18px;
      }
      .composer .src-label { display: none; }
      .suggestions { padding: 8px 14px; overflow: hidden; }
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
    .graph-vis-wrap {
      border: 1px solid #e8eaed;
      border-radius: 10px;
      background: #f8f9fa;
      min-height: 400px;
      max-height: 600px;
      min-width: 0;
      overflow: hidden;
    }
    .graph-vis-wrap #graphVis { width: 100%; height: 400px; }
    .graph-stats {
      font-size: 12px; color: #9aa0a6;
      text-align: center;
    }
    .graph-neo4j-link {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 12px; color: #1a73e8; text-decoration: none;
      cursor: pointer; margin-top: 4px;
    }
    .graph-neo4j-link:hover { text-decoration: underline; }
    @media (max-width: 860px) {
      .graph-panel { width: 100%; }
      .graph-vis-wrap { min-height: 320px; }
      .graph-vis-wrap #graphVis { height: 320px; }
    }
    @media (max-width: 420px) {
      .top-actions { gap: 2px; }
      .chat-top button { width: 30px; height: 30px; }
      .bubble { border-radius: 14px; padding: 10px 12px; }
      .answer-card { padding: 10px; border-radius: 10px; }
      table.data { font-size: 12px; }
    }
  </style>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
  <div class="drop-overlay" id="dropOverlay">Перетащите файлы сюда</div>
  <input type="file" id="fileInput" multiple accept=".json,.jsonl,.csv,.tsv,.txt,.md" style="display:none">
  <div class="app" id="appShell">
    <aside class="sources">
      <div class="sources-top">
        <span>Источники</span>
        <button id="collapseSources" title="Свернуть">&#9634;</button>
      </div>
      <button class="add-sources" id="addSources">
        <span class="plus">+</span> Добавить источники
      </button>
      <div class="source-tools">
        <input class="source-search" id="sourceSearch" type="search" placeholder="Найти источник" aria-label="Найти источник">
        <div class="source-actions">
          <div class="source-actions-group">
            <button class="source-action" id="selectAllSources" type="button">Все</button>
            <button class="source-action" id="selectNoSources" type="button">Ни один</button>
          </div>
          <span class="source-summary" id="sourceSummary">0 выбрано</span>
        </div>
      </div>
      <div class="upload-progress" id="uploadProgress">
        <div id="uploadProgressText">Загрузка файлов...</div>
        <div class="upload-progress-bar"><div class="upload-progress-fill" id="uploadProgressFill"></div></div>
      </div>
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
        <div class="top-actions">
          <button class="restore-sources" id="restoreSources" title="Показать источники">Источники</button>
          <button class="graph-toggle" id="graphToggle" title="Граф знаний">
            <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
          </button>
          <button id="menuButton" title="Меню">&vellip;</button>
          <div class="menu-popover" id="menuPopover">
            <button id="loadSample" type="button">Загрузить пример данных</button>
            <button id="clearAllSources" type="button">Удалить все источники</button>
            <button id="clearChat" type="button">Очистить чат</button>
          </div>
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
  <div class="graph-panel" id="graphPanel">
    <div class="graph-panel-top">
      <span>Граф знаний</span>
      <button class="graph-close" id="graphClose" title="Закрыть">&times;</button>
    </div>
    <div class="graph-body">
      <div class="graph-legend" id="graphLegend"></div>
      <div class="graph-vis-wrap"><div id="graphVis"></div></div>
      <div class="graph-stats" id="graphStats"></div>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const UI_CONFIG = {
      uploadBatchSize: 25,
      sourcePageSize: 160,
      maxChipRows: 20,
      maxListRows: 8,
      maxTableRows: 10,
      maxCitations: 8,
      supportedTypes: ["json", "jsonl", "csv", "tsv", "txt", "md"],
      graph: {
        colors: {
          material: "#1a73e8", property: "#34a853", mode: "#f9ab00",
          experiment: "#ea4335", equipment: "#9aa0a6", team: "#9334e6",
          document: "#fbbc04", tag: "#00897b"
        },
        labels: {
          material: "Материал", property: "Свойство", mode: "Режим",
          experiment: "Эксперимент", equipment: "Оборудование", team: "Команда",
          document: "Документ", tag: "Тег"
        }
      }
    };
    const UI_TEXT = {
      noData: "Нет данных",
      noMeasurements: "Измерения не найдены",
      noExperiments: "Эксперименты не найдены",
      noDecisionHistory: "История решений не найдена",
      noGaps: "Пробелы не найдены",
      answerMissing: "Ответ не сформирован.",
      citationsTitle: "Источники цитат",
      sourceEmptyTitle: "Здесь появятся загруженные источники",
      sourceEmptyBody: "Нажмите &laquo;Добавить источники&raquo; или перетащите файлы: JSON, JSONL, CSV, TSV, TXT, MD",
      sourceNotFoundTitle: "Источники не найдены",
      sourceNotFoundBody: "Измените строку поиска или загрузите другой файл.",
      graphEmpty: "Граф пуст — загрузите данные",
      graphLoadErrorHint: "Убедитесь что Neo4j запущен: docker compose up -d",
      sampleLoaded: "Пример данных загружен.",
      allSourcesRemoved: "Все источники удалены. Граф пуст.",
      filesAccepted: "источники приняты"
    };
    const state = {
      files: [],
      selected: new Set(),
      sourceFilter: "",
      sourceLimit: UI_CONFIG.sourcePageSize,
      total: 0
    };

    function escapeHtml(v) {
      return String(v ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
    }
    async function postJson(url, payload = {}) {
      const r = await fetch(url, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error(await r.text() || r.statusText);
      return r.json();
    }
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
      if ($("notebookMeta")) $("notebookMeta").textContent = totalText;
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
        return '<div class="source-row' + muted + '"><input type="checkbox" class="source-check"' + checked + ' data-name="' + escapeHtml(f.name) + '">' +
          '<div class="source-icon ' + t + '">' + t.toUpperCase() + "</div>" +
          '<div class="source-info"><b title="' + escapeHtml(f.name) + '">' + escapeHtml(f.name) + "</b><span>" + formatSize(f.size) + "</span></div>" +
          '<button class="source-delete" data-name="' + escapeHtml(f.name) + '" title="Удалить">&times;</button></div>';
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
      renderSourceList();
      if (uploadResult.overview && options.notify !== false) {
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
        '<div class="bubble">' + escapeHtml(data.answer||UI_TEXT.answerMissing) + "</div>" +
        (w ? '<div class="answer-card"><h3>Предупреждения</h3><div class="chips">' + w + "</div></div>" : "") +
        '<div class="answer-card"><h3>Найденные сущности</h3>' + chipList(data.matched_entities) + "</div>" +
        '<div class="answer-card"><h3>Что уже делали</h3>' + listBlock(data.experiments, r => "<b>" + escapeHtml(r.canonical_name) + "</b><span>" + escapeHtml(r.id) + "</span>", UI_TEXT.noExperiments) + "</div>" +
        '<div class="answer-card"><h3>Эффект и измерения</h3>' + tableBlock(data.observations) + "</div>" +
        (citations ? '<div class="answer-card">' + citations + "</div>" : "") +
        '<div class="answer-card"><h3>Связанные сущности</h3>' + chipList(data.related_entities) + "</div>" +
        '<div class="answer-card"><h3>История решений</h3>' + listBlock(data.decision_history, r => "<b>" + escapeHtml(r.summary) + "</b><span>" + escapeHtml(r.decision||"вывод") + "</span>", UI_TEXT.noDecisionHistory) + "</div>" +
        '<div class="answer-card"><h3>Пробелы данных</h3>' + listBlock(data.data_gaps, r => "<b>" + escapeHtml(r.reason) + "</b><span>" + escapeHtml(r.scope) + "</span>", UI_TEXT.noGaps) + "</div>"
      );
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
      const totals = { entities: 0, experiments: 0, documents: 0 };
      let lastOverview = null;
      let lastQuestions = [];
      let uploadedCount = 0;
      try {
        for (let offset = 0; offset < files.length; offset += UI_CONFIG.uploadBatchSize) {
          const batch = files.slice(offset, offset + UI_CONFIG.uploadBatchSize);
          const fd = new FormData();
          for (const f of batch) fd.append("files", f);
          setUploadProgress(uploadedCount, files.length, "Загрузка " + (offset + 1) + "-" + Math.min(offset + batch.length, files.length) + " из " + files.length);
          const r = await fetch("/ingest/upload", { method: "POST", body: fd });
          if (!r.ok) throw new Error(await r.text() || r.statusText);
          const data = await r.json();
          uploadedCount += batch.length;
          totals.entities += data.reference?.entities || 0;
          totals.experiments += data.experiments?.experiments || 0;
          totals.documents += data.documents?.documents || 0;
          lastOverview = data.overview || lastOverview;
          lastQuestions = data.suggested_questions || lastQuestions;
          renderSources(data, { notify: false });
          setUploadProgress(uploadedCount, files.length, "Загружено " + uploadedCount + " из " + files.length);
          await new Promise(resolve => setTimeout(resolve, 0));
        }
        const counts = [];
        if (totals.entities) counts.push(totals.entities + " сущностей");
        if (totals.experiments) counts.push(totals.experiments + " экспериментов");
        if (totals.documents) counts.push(totals.documents + " документов");
        if (lastOverview) addMsg("assistant", '<div class="overview-card">' + escapeHtml(lastOverview.summary) + "</div>");
        if (lastQuestions.length) renderSuggestions(lastQuestions);
        addMsg("assistant", '<div class="bubble">Готово: ' + formatCount(files.length, "файл", "файла", "файлов") + ". " + (counts.join(", ") || UI_TEXT.filesAccepted) + ".</div>");
      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      } finally {
        $("uploadProgress").classList.remove("active");
        $("uploadProgressFill").style.width = "0%";
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
    async function loadSampleData() {
      $("menuPopover").classList.remove("open");
      $("loadSample").disabled = true;
      try {
        const data = await postJson("/demo/load-sample");
        renderSources(data);
        const firstQuestion = data.suggested_questions?.[0];
        addMsg("assistant", '<div class="bubble">' + UI_TEXT.sampleLoaded + (firstQuestion ? " Первый вопрос уже в подсказках." : "") + "</div>");
      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      } finally {
        $("loadSample").disabled = false;
      }
    }
    async function deleteSource(name) {
      try {
        const r = await fetch("/sources/" + encodeURIComponent(name), { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text() || r.statusText);
        const data = await r.json();
        state.files = state.files.filter(f => f.name !== name);
        state.selected.delete(name);
        setSourceStats();
        renderSources({ uploaded: [], overview: data.overview, suggested_questions: [] });
        addMsg("assistant", '<div class="bubble">Источник "' + escapeHtml(name) + '" удалён. Удалено записей: ' + data.removed_records + "</div>");

      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      }
    }
    async function clearAllSources() {
      try {
        const r = await fetch("/sources", { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text() || r.statusText);
        const data = await r.json();
        state.files = [];
        state.selected.clear();
        state.sourceLimit = UI_CONFIG.sourcePageSize;
        setSourceStats();
        renderSourceList();
        addMsg("assistant", '<div class="bubble">' + UI_TEXT.allSourcesRemoved + "</div>");

        if (data.suggested_questions?.length) renderSuggestions(data.suggested_questions);
      } catch(e) {
        addMsg("assistant", '<div class="bubble error">' + escapeHtml(e.message) + "</div>");
      }
    }
    function clearChat() {
      $("menuPopover").classList.remove("open");
      $("chatBody").innerHTML = '<div class="hero" id="hero"><div class="hero-inner"><div class="hero-icon">&#128218;</div><h1>Блокнот материалов</h1><p id="notebookMeta">' + formatCount(state.total, "источник", "источника", "источников") + '</p></div></div><div class="suggestions" id="suggestions"></div>';
      fetch("/source/suggestions").then(r => r.json()).then(renderSuggestions).catch(() => {});
    }
    $("addSources").addEventListener("click", () => $("fileInput").click());
    $("fileInput").addEventListener("change", e => { uploadFiles(Array.from(e.target.files)); e.target.value = ""; });
    $("sendQuestion").addEventListener("click", ask);
    $("question").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
    $("question").addEventListener("input", function() { this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 120) + "px"; });
    $("collapseSources").addEventListener("click", () => $("appShell").classList.add("sources-collapsed"));
    $("restoreSources").addEventListener("click", () => $("appShell").classList.remove("sources-collapsed"));
    $("menuButton").addEventListener("click", e => { e.stopPropagation(); $("menuPopover").classList.toggle("open"); });
    $("loadSample").addEventListener("click", loadSampleData);
    $("clearAllSources").addEventListener("click", () => { $("menuPopover").classList.remove("open"); clearAllSources(); });
    $("clearChat").addEventListener("click", clearChat);
    $("sourceSearch").addEventListener("input", e => {
      state.sourceFilter = e.target.value;
      state.sourceLimit = UI_CONFIG.sourcePageSize;
      renderSourceList();
    });
    $("selectAllSources").addEventListener("click", () => {
      state.files.forEach(f => state.selected.add(f.name));
      renderSourceList();
    });
    $("selectNoSources").addEventListener("click", () => {
      state.selected.clear();
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
    function buildLegend() {
      $("graphLegend").innerHTML = Object.keys(UI_CONFIG.graph.colors).map(k =>
        '<span class="legend-item"><span class="legend-dot" style="background:' + UI_CONFIG.graph.colors[k] + '"></span>' + (UI_CONFIG.graph.labels[k]||k) + '</span>'
      ).join("");
    }
    async function loadGraph() {
      $("graphStats").textContent = "Загрузка графа...";
      try {
        const resp = await fetch("/graph/data");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        const nodes = data.nodes || [];
        const edges = data.edges || [];
        if (!nodes.length) {
          $("graphVis").innerHTML = '<div style="padding:40px;text-align:center;color:#9aa0a6">Граф пуст — загрузите данные</div>';
          $("graphStats").textContent = "0 узлов, 0 связей";
          return;
        }
        const nodesMap = {};
        nodes.forEach(n => { nodesMap[n.id] = n; });
        const visNodes = nodes.map(n => ({
          id: n.id,
          label: (n.name || n.id).substring(0, 25),
          title: n.name + " (" + n.kind + ")",
          color: { background: "#fff", border: UI_CONFIG.graph.colors[n.kind] || "#5f6368", highlight: { border: "#1a73e8" } },
          borderWidth: 2,
          font: { size: 11, color: "#202124" },
          shape: "dot",
          size: 12,
        }));
        const visEdges = edges.map(e => ({
          id: e.id,
          from: e.source,
          to: e.target,
          label: e.type,
          title: e.type,
          arrows: "to",
          color: { color: "#9aa0a6", opacity: 0.5 },
          font: { size: 9, color: "#9aa0a6", strokeWidth: 0 },
        }));
        const container = $("graphVis");
        const network = new vis.Network(container, { nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) }, {
          physics: { barnesHut: { gravitationalConstant: -3000, springLength: 150, springConstant: 0.02 }, stabilization: { iterations: 100 } },
          interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
          nodes: { font: { face: "system-ui" } },
          edges: { smooth: { type: "continuous" } },
        });
        $("graphStats").textContent = visNodes.length + " узлов, " + visEdges.length + " связей";
      } catch(e) {
        $("graphVis").innerHTML = '<div style="padding:40px;text-align:center;color:#d93025">Ошибка: ' + escapeHtml(e.message) + '<br>Убедитесь что Neo4j запущен: docker compose up -d</div>';
        $("graphStats").textContent = "";
      }
    }
    $("graphToggle").addEventListener("click", () => {
      $("graphPanel").classList.toggle("open");
      if ($("graphPanel").classList.contains("open")) {
        buildLegend();
        loadGraph();
      }
    });
    $("graphClose").addEventListener("click", () => {
      $("graphPanel").classList.remove("open");
    });
    async function loadInitialState() {
      try {
        const r = await fetch("/state");
        if (!r.ok) return;
        const data = await r.json();
        if (data.source_files?.length) {
          mergeFiles(data.source_files);
          renderSourceList();
          if (data.overview?.summary) {
            addMsg("assistant", '<div class="overview-card">' + escapeHtml(data.overview.summary) + "</div>");
          }
          if (data.suggested_questions?.length) renderSuggestions(data.suggested_questions);
        }
      } catch(e) { /* silent on startup */ }
    }
    loadInitialState();
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


def _create_session_store():
    """Create session store with TTL from settings."""
    try:
        from kg_engine.services.session import SessionStore
        from kg_engine.config.settings import settings

        return SessionStore(
            ttl_seconds=settings.session_ttl_seconds,
            max_messages=settings.session_max_messages,
        )
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
        session_store=_create_session_store(),
    )
    app = FastAPI(title=api_title)
    _source_files: list[dict] = []

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

    @app.get("/state")
    def get_state() -> dict:
        overview = runtime_service.get_source_overview()
        return {
            "source_files": list(_source_files),
            "overview": overview,
            "suggested_questions": runtime_service.get_suggested_questions(),
        }

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
            uploaded.append(
                {
                    "name": name,
                    "size": len(content),
                    "type": suffix.lstrip(".") or "unknown",
                }
            )
            if parsed is None:
                doc_payload.append(
                    {
                        "document_id": name,
                        "title": Path(name).stem,
                        "text": content.decode("utf-8", errors="replace"),
                        "metadata": {"source_file": name},
                    }
                )
                continue
            if suffix in _TEXT_SUFFIXES:
                items = parsed if isinstance(parsed, list) else [parsed]
                for item in items:
                    if isinstance(item, dict):
                        item["_uploaded_from"] = name
                        item.setdefault("metadata", {})["source_file"] = name
                if isinstance(parsed, list):
                    doc_payload.extend(items)
                else:
                    doc_payload.append(parsed)
                continue
            if isinstance(parsed, dict):
                for key in (
                    "entities",
                    "materials",
                    "equipment",
                    "properties",
                    "modes",
                    "teams",
                    "documents",
                    "tags",
                    "coverage_rules",
                ):
                    if key in parsed and isinstance(parsed[key], list):
                        for item in parsed[key]:
                            item["_uploaded_from"] = name
                        ref_payload.setdefault(key, []).extend(parsed[key])
                if "experiments" in parsed and isinstance(parsed["experiments"], list):
                    for item in parsed["experiments"]:
                        item["_uploaded_from"] = name
                    exp_payload.extend(parsed["experiments"])
                if "documents" in parsed and isinstance(parsed["documents"], list):
                    for item in parsed["documents"]:
                        item["_uploaded_from"] = name
                    doc_payload.extend(parsed["documents"])
                if not any(
                    k in parsed
                    for k in ("entities", "materials", "experiments", "documents")
                ):
                    if (
                        parsed.get("kind")
                        or parsed.get("entity_kind")
                        or parsed.get("type")
                    ):
                        parsed["_uploaded_from"] = name
                        ref_payload.setdefault("entities", []).append(parsed)
                    else:
                        doc_payload.append(
                            {
                                "document_id": name,
                                "title": Path(name).stem,
                                "text": json.dumps(parsed, ensure_ascii=False),
                                "metadata": {"source_file": name},
                            }
                        )
            elif isinstance(parsed, list):
                for item_index, item in enumerate(parsed):
                    if not isinstance(item, dict):
                        continue
                    if item.get("kind") or item.get("entity_kind") or item.get("type"):
                        item["_uploaded_from"] = name
                        ref_payload.setdefault("entities", []).append(item)
                    elif (item.get("experiment_id") or item.get("id")) and (
                        item.get("material_name") or item.get("material")
                    ):
                        item["_uploaded_from"] = name
                        exp_payload.append(item)
                    elif (
                        item.get("document_id")
                        or item.get("text")
                        or item.get("content")
                    ):
                        doc_payload.append(item)
                    else:
                        doc_payload.append(
                            {
                                "document_id": f"{name}#row-{item_index}",
                                "title": f"{Path(name).stem} #row-{item_index}",
                                "text": json.dumps(item, ensure_ascii=False),
                                "metadata": {"source_file": name},
                            }
                        )
        results = {}
        if ref_payload:
            results["reference"] = runtime_service.ingest_reference_data(
                ReferenceDataAdapter().from_payload(ref_payload)
            )
        if exp_payload:
            results["experiments"] = runtime_service.ingest_experiments(
                ExperimentCatalogAdapter().from_payload(exp_payload)
            )
        if doc_payload:
            results["documents"] = runtime_service.ingest_documents(
                DocumentCorpusAdapter().from_payload(doc_payload)
            )
        results["uploaded"] = uploaded
        results["overview"] = runtime_service.get_source_overview()
        results["suggested_questions"] = runtime_service.get_suggested_questions()
        _source_files.extend(uploaded)
        return results

    @app.post("/demo/load-sample")
    def load_sample_data() -> dict:
        reference_path = _SAMPLE_DATA_DIR / "reference.json"
        experiments_path = _SAMPLE_DATA_DIR / "experiments.json"
        documents_path = _SAMPLE_DATA_DIR / "documents.json"
        with reference_path.open("r", encoding="utf-8") as file:
            reference_payload = json.load(file)
        with experiments_path.open("r", encoding="utf-8") as file:
            experiments_payload = json.load(file)
        with documents_path.open("r", encoding="utf-8") as file:
            documents_payload = json.load(file)

        for section_key in (
            "entities",
            "materials",
            "equipment",
            "properties",
            "modes",
            "teams",
            "documents",
            "tags",
            "coverage_rules",
        ):
            for item in reference_payload.get(section_key, []):
                item.setdefault("source_ref", reference_path.name)
        exp_items = (
            experiments_payload.get("experiments", [])
            if isinstance(experiments_payload, dict)
            else experiments_payload
        )
        for item in exp_items:
            if isinstance(item, dict):
                item.setdefault("source_ref", experiments_path.name)
        doc_items = (
            documents_payload.get("documents", [])
            if isinstance(documents_payload, dict)
            else documents_payload
        )
        for item in doc_items:
            if isinstance(item, dict):
                item.setdefault("source_ref", documents_path.name)

        results = {
            "reference": runtime_service.ingest_reference_data(
                ReferenceDataAdapter().from_payload(reference_payload)
            ),
            "experiments": runtime_service.ingest_experiments(
                ExperimentCatalogAdapter().from_payload(experiments_payload)
            ),
            "documents": runtime_service.ingest_documents(
                DocumentCorpusAdapter().from_payload(documents_payload)
            ),
            "uploaded": [
                {
                    "name": reference_path.name,
                    "size": reference_path.stat().st_size,
                    "type": "json",
                },
                {
                    "name": experiments_path.name,
                    "size": experiments_path.stat().st_size,
                    "type": "json",
                },
                {
                    "name": documents_path.name,
                    "size": documents_path.stat().st_size,
                    "type": "json",
                },
            ],
        }
        results["overview"] = runtime_service.get_source_overview()
        results["suggested_questions"] = runtime_service.get_suggested_questions()
        _source_files.extend(results["uploaded"])
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
            session_id=request.session_id,
        )

    @app.post("/query/answer/stream")
    async def query_answer_stream(request: AnswerQueryRequest):
        from fastapi.responses import StreamingResponse

        async def generate():
            async for chunk in runtime_service.answer_question_stream(
                question=request.question,
                material=request.material,
                mode=request.mode,
                property_name=request.property_name,
                source_ids=request.source_ids,
                session_id=request.session_id,
            ):
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.post("/hypotheses/generate")
    def generate_hypotheses(request: HypothesisInput) -> dict:
        return runtime_service.generate_hypotheses(request).model_dump(mode="json")

    @app.get("/source/overview")
    def source_overview() -> dict:
        overview = runtime_service.get_source_overview()
        overview["uploaded_files"] = list(_source_files)
        return overview

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

    @app.get("/sources")
    def list_sources() -> list[dict]:
        return list(_source_files)

    @app.delete("/sources/{source_name}")
    def delete_source(source_name: str) -> dict:
        if not getattr(runtime_settings, "materials_enable_destructive_api", False):
            return Response(
                content='{"error": "Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true."}',
                status_code=403,
                media_type="application/json",
            )
        removed = runtime_service._repository.delete_source(source_name)  # noqa: SLF001
        _source_files[:] = [s for s in _source_files if s.get("name") != source_name]
        return {
            "deleted": source_name,
            "removed_records": removed,
            "overview": runtime_service.get_source_overview(),
        }

    @app.delete("/sources")
    def clear_all_sources() -> dict:
        if not getattr(runtime_settings, "materials_enable_destructive_api", False):
            return Response(
                content='{"error": "Destructive API disabled. Set MATERIALS_ENABLE_DESTRUCTIVE_API=true."}',
                status_code=403,
                media_type="application/json",
            )
        runtime_service._repository.clear_all()  # noqa: SLF001
        _source_files.clear()
        return {
            "cleared": True,
            "overview": runtime_service.get_source_overview(),
            "suggested_questions": runtime_service.get_suggested_questions(),
        }

    return app
