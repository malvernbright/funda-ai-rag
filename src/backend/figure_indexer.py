"""
Figure indexing for Funda AI Tutor.

Pulls embedded pictures (diagrams, maps, graphs, photos) out of textbook PDFs, has a vision model
write a searchable caption for each one, and returns them as Documents for the Chroma index.
At question time the best-matching figures are shown to the student with the answer.

Notes
* Pages that are one big scanned image are skipped (no separate figure to extract).
* Captioning prefers a LOCAL Ollama vision model (free, offline) and falls back to Gemini.
* Set FIGURE_INDEXING=0 to switch the whole feature off.
"""
import os
import time

from langchain_core.documents import Document
from backend.model_router import prepare_image, describe_images

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIGURES_DIR = os.path.join(BASE_DIR, "figures")

FIGURE_INDEXING = os.getenv("FIGURE_INDEXING", "1") == "1"
MAX_FIGURES_PER_FILE = int(os.getenv("FIGURES_MAX_PER_FILE", "150"))
MIN_SIDE = int(os.getenv("FIGURE_MIN_SIDE", "120"))          # skip icons / bullets / rules
MAX_PAGE_COVER = float(os.getenv("FIGURE_MAX_PAGE_COVER", "0.85"))  # skip full-page scans
CAPTION_PAUSE = float(os.getenv("FIGURE_CAPTION_PAUSE", "0.5"))     # raise if Gemini rate-limits you
MAX_CONSECUTIVE_FAILURES = 3

_CAPTION_PROMPT = (
    "This image comes from page {page} of a Zimbabwe school textbook ({subject}).\n"
    "Text from the same page, for context:\n{context}\n\n"
    "Write a caption that will be used to SEARCH for this figure. In 2-4 sentences say what kind of figure it is "
    "(diagram, map, graph, table, photo, drawing), transcribe any title and labels exactly, and explain what it shows.\n"
    "If it is only decoration (logo, border, background, icon, blank), reply with exactly: SKIP"
)


def _marker(meta: dict) -> str:
    return os.path.join(FIGURES_DIR, meta["level"], meta["subject"],
                        f"{meta['original_name']}_v{meta['version']}.done")


def figures_done(meta: dict) -> bool:
    return os.path.exists(_marker(meta))


def mark_figures_done(meta: dict):
    path = _marker(meta)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def _extract(file_path: str):
    """Yield (page_index, raw_bytes, mime) for each real figure in the PDF."""
    import fitz  # PyMuPDF

    pdf = fitz.open(file_path)
    seen, count = set(), 0
    try:
        for page_index, page in enumerate(pdf):
            page_area = (page.rect.width * page.rect.height) or 1
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:          # logos / headers repeat on many pages
                    continue
                seen.add(xref)
                try:
                    rects = page.get_image_rects(xref)
                    if rects and max(r.width * r.height for r in rects) / page_area > MAX_PAGE_COVER:
                        continue
                    pix = fitz.Pixmap(pdf, xref)
                    if pix.width < MIN_SIDE or pix.height < MIN_SIDE:
                        continue
                    if pix.alpha:
                        pix = fitz.Pixmap(pix, 0)
                    if pix.n - pix.alpha >= 4:           # CMYK -> RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    raw, mime = prepare_image(pix.tobytes("png"), "image/png")
                except Exception as e:
                    print(f"⚠️ Could not read image {xref} on page {page_index + 1}: {e}")
                    continue
                yield page_index, raw, mime
                count += 1
                if count >= MAX_FIGURES_PER_FILE:
                    return
    finally:
        pdf.close()


def build_figure_docs(file_path: str, meta: dict, page_docs) -> list:
    """Caption every figure in the PDF and return Documents (type='figure') ready to embed."""
    try:
        import fitz  # noqa: F401
    except Exception as e:
        print(f"⚠️ Figure indexing needs PyMuPDF ({e}). pip install pymupdf")
        return []

    page_text = {d.metadata.get("page", i): d.page_content for i, d in enumerate(page_docs)}
    out_dir = os.path.join(FIGURES_DIR, meta["level"], meta["subject"])
    os.makedirs(out_dir, exist_ok=True)

    docs, failures = [], 0
    for n, (page_index, raw, mime) in enumerate(_extract(file_path), start=1):
        prompt = _CAPTION_PROMPT.format(
            page=page_index + 1,
            subject=meta["subject"].replace("_", " "),
            context=(page_text.get(page_index, "") or "(no text)")[:600],
        )
        try:
            caption = describe_images([(raw, mime)], prompt=prompt, prefer_local=True).strip()
            failures = 0
        except Exception as e:
            failures += 1
            print(f"⚠️ Captioning failed on page {page_index + 1}: {e}")
            if failures >= MAX_CONSECUTIVE_FAILURES:
                print("❌ Stopping figure indexing for this file: no vision model is responding.")
                break
            continue

        if caption.upper().startswith("SKIP") or len(caption) < 20:
            continue

        filename = f"{meta['original_name']}_v{meta['version']}_p{page_index + 1}_{n}.jpg"
        with open(os.path.join(out_dir, filename), "wb") as f:
            f.write(raw)

        docs.append(Document(
            page_content=f"Figure on page {page_index + 1}: {caption}",
            metadata={
                "type": "figure",
                "page": page_index,
                "page_number": page_index + 1,
                "figure_path": "/".join(["figures", meta["level"], meta["subject"], filename]),
            },
        ))
        time.sleep(CAPTION_PAUSE)

    print(f"🖼️ {os.path.basename(file_path)}: {len(docs)} figures captioned")
    return docs