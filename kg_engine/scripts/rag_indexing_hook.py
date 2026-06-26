"""
MkDocs hook to export Jinja2-compiled markdown for RAG indexing.
Place this in MkDocs project root or .rag_export/ folder.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml


def on_page_markdown(markdown, page, config, files):  # noqa: D401, ANN001
    """Called AFTER Jinja2 processing, BEFORE HTML conversion."""
    page._compiled_md_for_rag = markdown
    return markdown


def on_post_page(output, page, config):  # noqa: D401, ANN001
    """Save compiled markdown to RAG folder."""
    try:
        compiled_md = getattr(page, "_compiled_md_for_rag", page.markdown)
        output_dir = Path(config["site_dir"])
        rel_path = Path(page.file.src_path)
        output_file = output_dir / rel_path
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            if page.meta:
                f.write("---\n")
                yaml.dump(page.meta, f, allow_unicode=True, default_flow_style=False)
                f.write("---\n\n")
            f.write(compiled_md)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to export {page.file.src_path}: {exc}")
    return output


def on_post_build(config):  # noqa: D401, ANN001
    """Create manifest for RAG indexer."""
    output_dir = Path(config["site_dir"])
    md_files = sorted(output_dir.rglob("*.md"))
    manifest = {
        "total_files": len(md_files),
        "files": [str(f.relative_to(output_dir)) for f in md_files],
        "build_date": datetime.now().isoformat(),
        "config_name": config.get("site_name"),
        "source_type": "mkdocs_pipeline",
    }
    with open(output_dir / "rag_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"RAG Export: {len(md_files)} compiled MD files → {output_dir}")


