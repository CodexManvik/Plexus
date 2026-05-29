"""
document_parser.py — Layout-aware document parsing with deterministic coordinate indexing.

Architecture:
  - PDF: PyMuPDF (fitz) only. CPU-bound, zero VRAM usage.
    * Text extracted line-by-line via page.get_text("rawdict") for sub-word glyph precision.
    * Tables extracted via page.find_tables() — native C-level grid detection, no ML.
    * Lines are accumulated into semantic chunks using Layout-Aware Semantic Accumulation:
      a 400–512 token window with forced breaks on structural signals (header font size
      delta, vertical spacing gap above threshold).
    * Each accumulated chunk maps its global (start_offset, end_offset) character range
      to a list of per-line bounding boxes: [[page, x0, y0, x1, y1, pw, ph], ...].
      The frontend uses these multi-segment line arrays for precise horizontal highlighting.
  - DOCX / XLSX / PPTX / all other non-PDF: Microsoft MarkItDown.
    MarkItDown converts Office formats to markdown and returns the plain text.
    coord_index is always an empty dict for non-PDF paths.
  - Optional Marker-PDF: activated only when USE_MARKER_PARSER=true in .env AND the
    marker-pdf package is manually installed. Falls back to PyMuPDF silently.

Exported symbols:
  CoordIndex  — type alias for the coordinate mapping dict.
  extract_document_text(file_name, content_type, file_bytes)
              → tuple[str, CoordIndex]
"""
from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# ── PyMuPDF — imported at module level so all helper functions can reference it.
# The install name is `pymupdf` but the import alias is `fitz` (historical PyMuPDF convention).
try:
    import fitz  # type: ignore  # pip install pymupdf>=1.24.0
    _FITZ_AVAILABLE: bool = True
    # TEXT_PRESERVE_WHITESPACE is an int flag (value 1).  Cache it here to avoid
    # repeated attribute lookups and to remain accessible even if fitz is monkey-patched.
    _FITZ_TEXT_FLAG: int = fitz.TEXT_PRESERVE_WHITESPACE
except ImportError:
    fitz = None  # type: ignore
    _FITZ_AVAILABLE = False
    _FITZ_TEXT_FLAG = 1  # Raw integer value — safe fallback.

# CoordIndex maps (start_char_offset, end_char_offset) → list of line-coordinate arrays.
# Each inner list element is [page_num, x0, y0, x1, y1, page_width, page_height].
# A single chunk may span multiple lines, so the value is a list-of-lists.
CoordIndex = dict[tuple[int, int], list[list[float]]]

# Approximate characters per token (conservative estimate for English legal text).
_CHARS_PER_TOKEN: float = 4.5
_CHUNK_TOKEN_MIN: int = 400
_CHUNK_TOKEN_MAX: int = 512
_CHUNK_CHAR_MIN: int = int(_CHUNK_TOKEN_MIN * _CHARS_PER_TOKEN)  # ~1800
_CHUNK_CHAR_MAX: int = int(_CHUNK_TOKEN_MAX * _CHARS_PER_TOKEN)  # ~2304

# Vertical gap (in points) that signals a structural section break between lines.
_SECTION_BREAK_GAP_PT: float = 14.0

# Font-size delta that flags a line as a heading/major structural marker.
_HEADING_FONT_SIZE_DELTA: float = 2.0



# ── Internal dataclass for a parsed line ─────────────────────────────────────

@dataclass
class _ParsedLine:
    text: str
    page_num: int
    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float
    page_height: float
    font_size: float
    is_table_cell: bool = False

    def coord_array(self) -> list[float]:
        return [
            float(self.page_num),
            self.x0, self.y0, self.x1, self.y1,
            self.page_width, self.page_height,
        ]


@dataclass
class _Chunk:
    lines: list[_ParsedLine] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(ln.text for ln in self.lines if ln.text.strip())

    @property
    def char_len(self) -> int:
        return len(self.text)

    def coord_arrays(self) -> list[list[float]]:
        return [ln.coord_array() for ln in self.lines if ln.text.strip()]


# ── PyMuPDF extraction ────────────────────────────────────────────────────────

def _is_structural_break(prev: Optional[_ParsedLine], curr: _ParsedLine) -> bool:
    """
    Returns True when the transition between `prev` and `curr` signals a major
    structural boundary: large vertical gap or significant font-size increase.
    """
    if prev is None:
        return False
    # Page boundary is always a structural break.
    if curr.page_num != prev.page_num:
        return True
    # Vertical gap threshold.
    vertical_gap = curr.y0 - prev.y1
    if vertical_gap > _SECTION_BREAK_GAP_PT:
        return True
    # Font-size jump upward (heading detected).
    if curr.font_size - prev.font_size > _HEADING_FONT_SIZE_DELTA:
        return True
    return False


def _extract_page_lines(page: "fitz.Page", page_num: int) -> list[_ParsedLine]:  # type: ignore[name-defined]
    """
    Extracts individual text lines from a PyMuPDF page.
    Uses rawdict for font-size access; falls back gracefully if unavailable.
    Table cells are extracted separately and merged in reading order.
    """
    pw = page.rect.width
    ph = page.rect.height
    parsed: list[_ParsedLine] = []

    # ── Regular text lines via rawdict ────────────────────────────────────────
    try:
        raw = page.get_text("rawdict", flags=_FITZ_TEXT_FLAG)
        for block in raw.get("blocks", []):
            if block.get("type") != 0:  # 0 = text block
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                line_text = "".join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue
                # Bounding box of the full line
                bbox = line.get("bbox", [0, 0, 0, 0])
                font_size = max(
                    (s.get("size", 10.0) for s in spans), default=10.0
                )
                parsed.append(_ParsedLine(
                    text=line_text,
                    page_num=page_num,
                    x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3],
                    page_width=pw, page_height=ph,
                    font_size=font_size,
                ))
    except Exception as exc:
        print(f"[Parser] rawdict extraction failed on page {page_num}: {exc}", file=sys.stderr)

    # ── Table cells via find_tables() ─────────────────────────────────────────
    try:
        tabs = page.find_tables()
        for table in tabs.tables:
            extracted = table.extract()
            if hasattr(table, 'rows') and table.rows:
                for row_idx, row in enumerate(table.rows):
                    if not hasattr(row, 'cells') or not row.cells:
                        continue
                    for col_idx, cell in enumerate(row.cells):
                        if cell is None:
                            continue
                        try:
                            cell_text = extracted[row_idx][col_idx]
                        except (IndexError, TypeError):
                            continue
                        if not cell_text or not str(cell_text).strip():
                            continue
                        parsed.append(_ParsedLine(
                            text=str(cell_text).strip(),
                            page_num=page_num,
                            x0=cell[0], y0=cell[1],
                            x1=cell[2], y1=cell[3],
                            page_width=pw, page_height=ph,
                            font_size=10.0,
                            is_table_cell=True,
                        ))
            else:
                # Fallback for older PyMuPDF: use whole-table bbox per cell
                for row in extracted:
                    for cell_text in row:
                        if not cell_text or not str(cell_text).strip():
                            continue
                        tb = table.bbox
                        parsed.append(_ParsedLine(
                            text=str(cell_text).strip(),
                            page_num=page_num,
                            x0=tb[0], y0=tb[1], x1=tb[2], y1=tb[3],
                            page_width=pw, page_height=ph,
                            font_size=10.0,
                            is_table_cell=True,
                        ))
    except Exception as exc:
        print(f"[Parser] find_tables() failed on page {page_num}: {exc}", file=sys.stderr)

    # Sort in reading order: top-to-bottom, left-to-right.
    parsed.sort(key=lambda ln: (ln.page_num, round(ln.y0, 1), ln.x0))
    return parsed


def _accumulate_chunks(all_lines: list[_ParsedLine]) -> list[_Chunk]:
    """
    Implements Layout-Aware Semantic Accumulation:
    Groups consecutive lines into chunks sized within [_CHUNK_CHAR_MIN, _CHUNK_CHAR_MAX].
    Forces a chunk break when a structural signal is detected (page change, large
    vertical gap, heading font-size jump) OR when the current chunk would exceed
    the max token window.
    """
    chunks: list[_Chunk] = []
    current = _Chunk()
    prev_line: Optional[_ParsedLine] = None

    for line in all_lines:
        force_break = _is_structural_break(prev_line, line)
        would_exceed = (current.char_len + len(line.text) + 1) > _CHUNK_CHAR_MAX

        if (force_break and current.char_len >= _CHUNK_CHAR_MIN) or \
                (would_exceed and current.char_len >= _CHUNK_CHAR_MIN):
            chunks.append(current)
            current = _Chunk()

        current.lines.append(line)
        prev_line = line

    if current.lines:
        chunks.append(current)

    return chunks


def _extract_pdf_text_with_index(file_bytes: bytes) -> tuple[str, CoordIndex]:
    """
    Full layout-aware PDF extraction.
    Returns:
        document_text — the full plain-text string of the document.
        coord_index   — CoordIndex mapping (start, end) char offsets to line coordinate arrays.
    """
    if not _FITZ_AVAILABLE:
        print(
            "[Parser] PyMuPDF (fitz) is not installed. Run: pip install pymupdf>=1.24.0",
            file=sys.stderr,
        )
        return "", {}

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        print(f"[Parser] fitz.open failed: {exc}", file=sys.stderr)
        return "", {}

    all_lines: list[_ParsedLine] = []
    for page_num, page in enumerate(doc, start=1):
        all_lines.extend(_extract_page_lines(page, page_num))
    doc.close()

    if not all_lines:
        return "", {}

    chunks = _accumulate_chunks(all_lines)

    # Build the document string and coordinate index simultaneously.
    fragments: list[str] = []
    coord_index: CoordIndex = {}
    cursor = 0

    for chunk in chunks:
        chunk_text = chunk.text
        if not chunk_text:
            continue
        start = cursor
        end = cursor + len(chunk_text)
        coord_index[(start, end)] = chunk.coord_arrays()
        fragments.append(chunk_text)
        cursor = end + 1  # +1 for the separator newline

    document_text = "\n".join(fragments)
    return document_text, coord_index


# ── Optional Marker-PDF integration ──────────────────────────────────────────

def _extract_pdf_marker(file_bytes: bytes) -> tuple[str, CoordIndex]:
    """
    High-fidelity table extraction via marker-pdf (CPU mode).
    Only called when USE_MARKER_PARSER=true and marker-pdf is installed.
    Produces a markdown string with preserved table structure.
    The coord_index is built by re-indexing marker's text blocks against
    PyMuPDF's geometry — see inline comments.

    WARNING: marker-pdf is NOT in requirements.txt. Install manually:
      pip install marker-pdf
    Torch will be pulled in; set device_map='cpu' to avoid VRAM usage.
    """
    try:
        from marker.convert import convert_single_pdf  # type: ignore
        from marker.models import load_all_models      # type: ignore
    except ImportError:
        print(
            "[Parser] marker-pdf not installed. Falling back to PyMuPDF. "
            "Install with: pip install marker-pdf",
            file=sys.stderr,
        )
        return _extract_pdf_text_with_index(file_bytes)

    try:
        import torch  # type: ignore
        device = "cpu"  # Enforce CPU per hardware constraint directive.
    except ImportError:
        device = "cpu"

    try:
        models = load_all_models(device=device)
        full_text, _, _ = convert_single_pdf(file_bytes, models, max_pages=None)
    except Exception as exc:
        print(f"[Parser] marker-pdf conversion failed: {exc}. Falling back to PyMuPDF.", file=sys.stderr)
        return _extract_pdf_text_with_index(file_bytes)

    # Marker doesn't expose per-block coordinates natively.
    # Strategy: build PyMuPDF coord_index separately and return Marker's richer text.
    # The coordinate index covers the full document via PyMuPDF independently.
    _, pymupdf_index = _extract_pdf_text_with_index(file_bytes)

    # The Marker text is the authoritative document_text; PyMuPDF index is best-effort spatial.
    # Callers that need exact citation coordinates will use the PyMuPDF index with fuzzy lookup.
    return full_text, pymupdf_index


# ── Non-PDF extraction via MarkItDown ────────────────────────────────────────

def _extract_non_pdf_text(file_bytes: bytes, file_name: str) -> tuple[str, CoordIndex]:
    """
    Converts any non-PDF document format (DOCX, XLSX, PPTX, etc.) to plain text
    using Microsoft MarkItDown. MarkItDown converts to markdown internally; we
    return the raw markdown string as the document text.

    coord_index is always empty for non-PDF formats — no spatial layout data
    is available from Office formats without per-format parsers.

    Falls back to UTF-8 decode if MarkItDown is not installed or raises.
    """
    try:
        from markitdown import MarkItDown  # type: ignore  # pip install markitdown
    except ImportError:
        print(
            "[Parser] markitdown not installed. Run: pip install markitdown>=0.1.1",
            file=sys.stderr,
        )
        # Hard fallback: best-effort UTF-8 decode.
        return file_bytes.decode("utf-8", errors="ignore").strip(), {}

    try:
        md = MarkItDown()
        # MarkItDown.convert() accepts a file-like object or a path.
        # We pass a BytesIO with the original filename so it can sniff the format.
        stream = io.BytesIO(file_bytes)
        stream.name = file_name  # type: ignore[attr-defined]  # MarkItDown reads .name for format detection
        result = md.convert(stream)
        text = (result.text_content or "").strip()
        return text, {}
    except Exception as exc:
        print(
            f"[Parser] MarkItDown conversion failed for '{file_name}': {exc}. "
            "Falling back to UTF-8 decode.",
            file=sys.stderr,
        )
        return file_bytes.decode("utf-8", errors="ignore").strip(), {}


# ── Public API ────────────────────────────────────────────────────────────────

def extract_document_text(
    file_name: str,
    content_type: Optional[str],
    file_bytes: bytes,
) -> Tuple[str, CoordIndex]:
    """
    Parses document bytes and returns (extracted_text, coord_index).

    coord_index is a CoordIndex dict — empty for non-PDF formats.
    For PDFs, keys are (start_char_offset, end_char_offset) character ranges
    relative to extracted_text; values are lists of per-line coordinate arrays
    [[page_num, x0, y0, x1, y1, page_width, page_height], ...] enabling
    precise multi-line frontend highlighting.

    Supported formats:
      Plain text  — TXT, CSV, JSON (returned as-is).
      PDF         — PyMuPDF layout-aware extraction (or Marker-PDF if configured).
      Office/Other — DOCX, XLSX, XLSM, PPTX, and any unrecognised format via
                     Microsoft MarkItDown. coord_index is empty for all these.
    """
    from app.config import settings  # late import to avoid circular deps at module load

    suffix = Path(file_name).suffix.lower()
    ctype = (content_type or "").lower()

    # ── Plain text formats: decode and return as-is ───────────────────────────
    if suffix in {".txt", ".csv", ".json"} or ctype.startswith("text/plain"):
        return file_bytes.decode("utf-8", errors="ignore").strip(), {}

    # ── PDF: layout-aware PyMuPDF pipeline (or optional Marker-PDF) ──────────
    if suffix == ".pdf" or ctype == "application/pdf":
        if settings.use_marker_parser:
            text, idx = _extract_pdf_marker(file_bytes)
        else:
            text, idx = _extract_pdf_text_with_index(file_bytes)
        return text.strip(), idx

    # ── All non-PDF office/binary formats: MarkItDown ─────────────────────────
    # Covers: .docx, .xlsx, .xlsm, .pptx, .ppt, .doc, .odt, and any other
    # format MarkItDown supports. coord_index is always {} for these paths.
    text, idx = _extract_non_pdf_text(file_bytes, file_name)
    return text.strip(), idx
