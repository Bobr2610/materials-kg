var UI_CONFIG = {
  uploadBatchSize: 25,
  sourcePageSize: 160,
  maxChipRows: 20,
  maxListRows: 8,
  maxTableRows: 10,
  maxCitations: 8,
  supportedTypes: ["json", "jsonl", "csv", "tsv", "txt", "md", "docx", "xlsx", "xls", "pdf", "html", "htm", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
  acceptAttribute: ".json,.jsonl,.csv,.tsv,.txt,.md,.docx,.xlsx,.xls,.pdf,.html,.htm,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp",
  endpoints: {
    upload: "/ingest/upload",
    queryAnswer: "/query/answer",
    sourceSuggestions: "/source/suggestions",
    hypothesesGenerate: "/hypotheses/generate",
    hypothesesJobBase: "/hypotheses/jobs/",
    hypothesesExport: "/hypotheses/export",
    loadTaskMaterials: "/demo/load-task-materials",
    loadTaskMaterialsJobBase: "/demo/load-task-materials/jobs/",
    graphData: "/graph/data",
    sources: "/sources",
    sourceDeleteBase: "/sources/",
    state: "/state",
    feedback: "/metrics/feedback"
  },
  taskMaterialsParams: {
    exclude_examples: "true",
    exclude_files: "Как читать отчет института по хвостам.docx",
    enable_vision: "true",
    enable_llm_extraction: "true",
    enable_embeddings: "false",
    parallel_workers: "1"
  },
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
