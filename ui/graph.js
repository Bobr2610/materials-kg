function closeGraphPanel() {
  $("graphPanel")?.classList.remove("open");
}

function refreshGraphIfOpen() {
  if ($("graphPanel")?.classList.contains("open")) loadGraph();
}

function showGraphEmpty(message) {
  const container = $("graphVis");
  if (container) container.innerHTML = '<div class="graph-empty">' + escapeHtml(message) + '</div>';
  if ($("graphStats")) $("graphStats").textContent = "0 узлов, 0 связей";
}

function graphDataUrl() {
  const selected = state.files.filter(f => state.selected.has(f.name)).map(f => f.name);
  if (!selected.length) return null;
  const params = new URLSearchParams();
  selected.forEach(name => params.append("sources", name));
  params.set("_", Date.now());
  return UI_CONFIG.endpoints.graphData + "?" + params.toString();
}

function buildLegend() {
  const el = $("graphLegend");
  if (!el) return;
  el.innerHTML = Object.keys(UI_CONFIG.graph.colors).map(k =>
    '<span class="legend-item"><span class="legend-dot" style="background:' + UI_CONFIG.graph.colors[k] + '"></span>' + (UI_CONFIG.graph.labels[k]||k) + '</span>'
  ).join("");
}

function buildLegendForNodes(nodes) {
  const el = $("graphLegend");
  if (!el) return;
  const kinds = Array.from(new Set((nodes || []).map(n => n.kind).filter(Boolean))).sort();
  el.innerHTML = kinds.map(k =>
    '<span class="legend-item"><span class="legend-dot" style="background:' + (UI_CONFIG.graph.colors[k] || "#5f6368") + '"></span>' + (UI_CONFIG.graph.labels[k]||k) + '</span>'
  ).join("");
}

async function loadGraph() {
  const stats = $("graphStats");
  if (!state.total) {
    showGraphEmpty(UI_TEXT.graphEmpty);
    return;
  }
  const url = graphDataUrl();
  if (!url) {
    showGraphEmpty(UI_TEXT.graphNoSelection);
    return;
  }
  if (stats) stats.textContent = "Загрузка графа...";
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    const nodes = data.nodes || [];
    const edges = data.edges || [];
    const container = $("graphVis");
    if (!container) return;
    buildLegendForNodes(nodes);
    if (!nodes.length) {
      showGraphEmpty(UI_TEXT.graphEmpty);
      return;
    }
    container.innerHTML = "";
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
      id: e.id, from: e.source, to: e.target, label: e.type, title: e.type,
      arrows: "to",
      color: { color: "#9aa0a6", opacity: 0.5 },
      font: { size: 9, color: "#9aa0a6", strokeWidth: 0 },
    }));
    new vis.Network(container, { nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) }, {
      physics: { barnesHut: { gravitationalConstant: -3000, springLength: 150, springConstant: 0.02 }, stabilization: { iterations: 100 } },
      interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
      nodes: { font: { face: "system-ui" } },
      edges: { smooth: { type: "continuous" } },
    });
    if (stats) stats.textContent = visNodes.length + " узлов, " + visEdges.length + " связей";
  } catch(e) {
    const container = $("graphVis");
    if (container) container.innerHTML = '<div class="graph-empty error">Ошибка: ' + escapeHtml(e.message) + '<br>' + UI_TEXT.graphLoadErrorHint + '</div>';
    if (stats) stats.textContent = "";
  }
}
