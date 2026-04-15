import logging
import re
import unicodedata

import fitz  # PyMuPDF

from app.config import settings


logger = logging.getLogger(__name__)

# Retry OCR once at a higher DPI if the first pass looks thin.
OCR_FIRST_DPI = 200
OCR_RETRY_DPI = 300
OCR_THIN_OUTPUT_CHARS = 80        # below this, worth retrying at higher DPI
OCR_LOW_CONFIDENCE_THRESHOLD = 0.6


def clean_ocr_text(raw: str) -> str:
    """
    Light post-OCR cleanup.

    - Strips zero-width / control chars.
    - De-hyphenates soft line-break hyphenation ("foo-\\nbar" -> "foobar"),
      which Cloud Vision preserves verbatim from column layouts.
    - Collapses runs of whitespace *within a line* (keeps paragraph breaks).
    - Drops lines that are mostly non-alphanumeric noise (page borders, rules).

    Intentionally conservative — common OCR confusions like 'rn' -> 'm' are
    NOT corrected here because they cause more harm than good on clean text.
    """
    if not raw:
        return ""

    # Remove control chars except \n and \t.
    text = "".join(
        ch for ch in raw
        if unicodedata.category(ch)[0] != "C" or ch in ("\n", "\t")
    )

    # De-hyphenate end-of-line breaks: "exam-\nple" -> "example"
    text = re.sub(r"-\n(?=\w)", "", text)

    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            cleaned_lines.append("")
            continue
        # Drop lines that are overwhelmingly punctuation / symbols (OCR borders).
        alnum = sum(1 for ch in line if ch.isalnum())
        if alnum == 0 or alnum / len(line) < 0.3:
            continue
        cleaned_lines.append(line)

    # Collapse 3+ consecutive blank lines into just one.
    collapsed: list[str] = []
    blank_streak = 0
    for line in cleaned_lines:
        if line == "":
            blank_streak += 1
            if blank_streak <= 1:
                collapsed.append(line)
        else:
            blank_streak = 0
            collapsed.append(line)

    return "\n".join(collapsed).strip()


def _ocr_with_cloud_vision(image_bytes: bytes, language_hints: list[str] | None) -> tuple[str, float]:
    """Call Cloud Vision document text detection. Returns (text, confidence)."""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    image_context = None
    if language_hints:
        image_context = vision.ImageContext(language_hints=language_hints)
    response = client.document_text_detection(image=image, image_context=image_context)
    if response.error.message:
        raise RuntimeError(f"Cloud Vision OCR failed: {response.error.message}")

    annotation = response.full_text_annotation
    if not annotation:
        return "", 0.0

    text = annotation.text or ""
    # Average page-level confidence if available; Cloud Vision exposes
    # `.confidence` on each page inside the annotation.
    confidences = [
        page.confidence
        for page in annotation.pages
        if getattr(page, "confidence", None) is not None
    ]
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    return text, float(avg_conf)


class PDFParser:
    """
    Extract text from PDFs.
    - Text-based pages: PyMuPDF (fast, accurate).
    - Scanned pages (low text density): Cloud Vision OCR with cleanup,
      adaptive DPI retry, and confidence-based source_type tagging.

    Returns a list of pages: [{page: int, text: str, source_type: str}, ...]
    where source_type is one of: "native", "ocr", "ocr_low_conf".
    """

    def __init__(self, language_hints: list[str] | None = None) -> None:
        # Order of precedence: explicit arg > config > English default.
        if language_hints is not None:
            self.language_hints = language_hints
        else:
            configured = getattr(settings, "ocr_language_hints", None) or ["en"]
            self.language_hints = list(configured)

    def extract(self, file_bytes: bytes) -> list[dict]:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages: list[dict] = []
        threshold = max(0, settings.extract_pdf_text_density_threshold)

        for page_num, page in enumerate(doc, start=1):
            native_text = page.get_text() or ""
            if len(native_text.strip()) >= threshold:
                pages.append({
                    "page": page_num,
                    "text": native_text,
                    "source_type": "native",
                })
                continue

            ocr_text, source_type = self._ocr_page(page)
            pages.append({
                "page": page_num,
                "text": ocr_text,
                "source_type": source_type,
            })

        doc.close()
        return pages

    def _ocr_page(self, page) -> tuple[str, str]:
        """Run OCR with one adaptive-DPI retry. Returns (cleaned_text, source_type)."""
        try:
            text, confidence = self._render_and_ocr(page, OCR_FIRST_DPI)
            if len(text.strip()) < OCR_THIN_OUTPUT_CHARS:
                # Very thin output — give it one retry at higher DPI before giving up.
                retry_text, retry_conf = self._render_and_ocr(page, OCR_RETRY_DPI)
                if len(retry_text.strip()) > len(text.strip()):
                    text = retry_text
                    confidence = retry_conf

            cleaned = clean_ocr_text(text)
            if not cleaned:
                return "", "ocr_low_conf"
            source_type = (
                "ocr_low_conf"
                if confidence and confidence < OCR_LOW_CONFIDENCE_THRESHOLD
                else "ocr"
            )
            if confidence and confidence < OCR_LOW_CONFIDENCE_THRESHOLD:
                logger.warning(
                    "Low-confidence OCR page (conf=%.2f, chars=%d)",
                    confidence,
                    len(cleaned),
                )
            return cleaned, source_type
        except Exception:
            logger.exception("OCR failed for page; returning empty text")
            return "", "ocr_low_conf"

    def _render_and_ocr(self, page, dpi: int) -> tuple[str, float]:
        pix = page.get_pixmap(dpi=dpi)
        image_bytes = pix.tobytes("png")
        return _ocr_with_cloud_vision(image_bytes, self.language_hints)
