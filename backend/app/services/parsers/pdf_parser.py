import fitz  # PyMuPDF


class PDFParser:
    """
    Extract text from PDFs.
    - Text-based pages: PyMuPDF (fast, accurate).
    - Scanned pages (low text density): Cloud Vision OCR.
    """

    TEXT_DENSITY_THRESHOLD = 50  # chars per page — below this triggers OCR

    def extract(self, file_bytes: bytes) -> list[dict]:
        """Return [{page: int, text: str}, ...] for every page."""
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pages = []
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if len(text.strip()) < self.TEXT_DENSITY_THRESHOLD:
                text = self._ocr_page(page)
            pages.append({"page": page_num, "text": text})
        doc.close()
        return pages

    def _ocr_page(self, page) -> str:
        """Use Google Cloud Vision to OCR a scanned page."""
        # TODO: render page to image, send to Cloud Vision, return text
        pix = page.get_pixmap(dpi=200)
        image_bytes = pix.tobytes("png")
        return _cloud_vision_ocr(image_bytes)


def _cloud_vision_ocr(image_bytes: bytes) -> str:
    """Call Google Cloud Vision document text detection."""
    from google.cloud import vision
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)
    response = client.document_text_detection(image=image)
    return response.full_text_annotation.text
