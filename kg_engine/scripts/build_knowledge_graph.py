"""Build knowledge graph from documents using entity extraction.

Usage:
    python kg_engine/scripts/build_knowledge_graph.py --source data/documents --output data/knowledge_graph.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from kg_engine.graph.pipeline import GraphPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Build materials knowledge graph from document chunks")
    parser.add_argument("--source", type=str, default=None, help="Path to JSON file with document chunks")
    parser.add_argument("--output", type=str, default="data/knowledge_graph.json", help="Output path for graph JSON")
    parser.add_argument("--use-llm", action="store_true", default=False, help="Use LLM for extraction (requires .env)")
    args = parser.parse_args()

    pipeline = GraphPipeline()

    if args.source:
        source_path = Path(args.source)
        if not source_path.exists():
            logger.error("Source file not found: %s", source_path)
            sys.exit(1)

        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chunks = data if isinstance(data, list) else data.get("chunks", data.get("documents", []))
        logger.info("Processing %d document chunks...", len(chunks))
        result = pipeline.index_chunks(chunks, use_llm=args.use_llm)
        logger.info("Indexed %d entities, %d relations", result["total_entities"], result["total_relations"])

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pipeline.save(str(output_path))

    stats = pipeline.stats()
    logger.info("Knowledge graph saved to %s", output_path)
    logger.info("Stats: %s", json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
