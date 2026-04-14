class TxtParser:
    """
    Extract text from plain .txt files.
    Tries UTF-8, falls back to latin-1. Splits into ~3000-char virtual pages
    at paragraph boundaries.
    """

    PAGE_CHAR_LIMIT = 3000

    def extract(self, file_bytes: bytes) -> list[dict]:
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")

        pages = []
        current = ""
        for para in text.split("\n\n"):
            current += para + "\n\n"
            if len(current) >= self.PAGE_CHAR_LIMIT:
                pages.append({"page": len(pages) + 1, "text": current.strip()})
                current = ""

        if current.strip():
            pages.append({"page": len(pages) + 1, "text": current.strip()})

        return pages
