"""Research PDF parser: prefer Marker, fall back to pypdf + structure heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ParsedBlock:
    text: str
    page_number: Optional[int] = None
    block_type: str = "paragraph"  # section | paragraph | table | figure
    section_title: str = ""
    figure_id: str = ""
    image_path: str = ""
    caption: str = ""


@dataclass
class ParsedDocument:
    title: str
    blocks: List[ParsedBlock] = field(default_factory=list)
    parser: str = "pypdf"
    full_text: str = ""


def _split_markdown_sections(markdown: str) -> List[ParsedBlock]:
    blocks: List[ParsedBlock] = []
    current_section = ""
    buffer: List[str] = []

    def flush_paragraph() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        buffer = []
        if not text:
            return
        block_type = "paragraph"
        figure_id = ""
        caption = ""
        image_path = ""

        fig_match = re.search(
            r"(?:Figure|Fig\.?|图)\s*([0-9]+(?:\.[0-9]+)?)\s*[:：.\-]?\s*(.*)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if fig_match and len(text) < 800:
            block_type = "figure"
            figure_id = f"Fig.{fig_match.group(1)}"
            caption = fig_match.group(2).strip() or text

        if re.search(r"(?:Table|表)\s*[0-9]", text, re.IGNORECASE) and "|" in text:
            block_type = "table"

        img_match = re.search(r"!\[[^\]]*\]\(([^)]+)\)", text)
        if img_match:
            block_type = "figure"
            image_path = img_match.group(1)
            if not caption:
                caption = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text).strip()

        blocks.append(
            ParsedBlock(
                text=text,
                block_type=block_type,
                section_title=current_section,
                figure_id=figure_id,
                image_path=image_path,
                caption=caption,
            )
        )

    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,3})\s+(.*)$", line.strip())
        if heading:
            flush_paragraph()
            current_section = heading.group(2).strip()
            blocks.append(
                ParsedBlock(
                    text=current_section,
                    block_type="section",
                    section_title=current_section,
                )
            )
            continue
        if not line.strip():
            flush_paragraph()
            continue
        buffer.append(line)
    flush_paragraph()
    return blocks


def _parse_with_marker(pdf_path: str, output_dir: Path) -> Optional[ParsedDocument]:
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        from marker.output import text_from_rendered
    except Exception as exc:
        print(f"[RAG] Marker unavailable: {exc}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(pdf_path)
        text, _, images = text_from_rendered(rendered)
        markdown = text if isinstance(text, str) else str(text)

        # Persist extracted images when Marker returns them
        image_map: dict[str, str] = {}
        if isinstance(images, dict):
            for name, image_obj in images.items():
                safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", str(name))
                out_path = output_dir / safe_name
                try:
                    if hasattr(image_obj, "save"):
                        image_obj.save(out_path)
                        image_map[str(name)] = str(out_path)
                except Exception:
                    continue

        blocks = _split_markdown_sections(markdown)
        # Attach saved image paths to figure-like blocks when possible
        unused = list(image_map.values())
        for block in blocks:
            if block.block_type == "figure" and not block.image_path and unused:
                block.image_path = unused.pop(0)
            elif block.image_path and block.image_path in image_map:
                block.image_path = image_map[block.image_path]

        title = Path(pdf_path).stem
        for block in blocks:
            if block.block_type == "section" and block.text:
                title = block.text
                break

        return ParsedDocument(
            title=title,
            blocks=blocks,
            parser="marker",
            full_text=markdown,
        )
    except Exception as exc:
        print(f"[RAG] Marker parse failed, fallback to pypdf: {exc}")
        return None


def _parse_with_pypdf(pdf_path: str) -> ParsedDocument:
    from rag.pdf_term_extractor import extract_text_from_pdf

    text = extract_text_from_pdf(pdf_path)
    # Heuristic: split by form-feed or double newlines into pages/sections
    pages = re.split(r"\f|\n{3,}", text)
    blocks: List[ParsedBlock] = []
    current_section = ""
    for page_idx, page_text in enumerate(pages, start=1):
        page_text = page_text.strip()
        if not page_text:
            continue
        for para in re.split(r"\n{2,}", page_text):
            para = para.strip()
            if not para:
                continue
            heading = re.match(r"^(\d+(?:\.\d+)*)\s+[A-Z一-龥].{3,80}$", para.split("\n", 1)[0])
            if heading or (len(para) < 80 and para.isupper()):
                current_section = para.split("\n", 1)[0].strip()
                blocks.append(
                    ParsedBlock(
                        text=current_section,
                        page_number=page_idx,
                        block_type="section",
                        section_title=current_section,
                    )
                )
                rest = "\n".join(para.split("\n")[1:]).strip()
                if rest:
                    blocks.append(
                        ParsedBlock(
                            text=rest,
                            page_number=page_idx,
                            block_type="paragraph",
                            section_title=current_section,
                        )
                    )
                continue

            fig_match = re.match(
                r"^(?:Figure|Fig\.?|图)\s*([0-9]+(?:\.[0-9]+)?)\s*[:：.\-]?\s*(.*)$",
                para,
                re.IGNORECASE | re.DOTALL,
            )
            if fig_match:
                blocks.append(
                    ParsedBlock(
                        text=para,
                        page_number=page_idx,
                        block_type="figure",
                        section_title=current_section,
                        figure_id=f"Fig.{fig_match.group(1)}",
                        caption=fig_match.group(2).strip() or para,
                    )
                )
                continue

            blocks.append(
                ParsedBlock(
                    text=para,
                    page_number=page_idx,
                    block_type="paragraph",
                    section_title=current_section,
                )
            )

    return ParsedDocument(
        title=Path(pdf_path).stem,
        blocks=blocks,
        parser="pypdf",
        full_text=text,
    )


def parse_research_pdf(pdf_path: str, output_dir: Optional[str] = None) -> ParsedDocument:
    """
    Parse a research PDF into structured blocks (sections/tables/figures).
    Prefers Marker; falls back to pypdf heuristics.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(pdf_path)

    out = Path(output_dir) if output_dir else path.parent / f"{path.stem}_assets"
    parsed = _parse_with_marker(str(path), out)
    if parsed is not None and parsed.blocks:
        return parsed
    return _parse_with_pypdf(str(path))
