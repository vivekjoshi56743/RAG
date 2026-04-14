from app.services.parsers.pdf_parser import PDFParser
from app.services.parsers.docx_parser import DocxParser
from app.services.parsers.txt_parser import TxtParser
from app.services.parsers.markdown_parser import MarkdownParser


class UnsupportedFileType(Exception):
    pass


PARSER_REGISTRY = {
    ".pdf":  PDFParser,
    ".docx": DocxParser,
    ".txt":  TxtParser,
    ".md":   MarkdownParser,
}


def get_parser(filename: str):
    ext = "." + filename.rsplit(".", 1)[-1].lower()
    parser_cls = PARSER_REGISTRY.get(ext)
    if not parser_cls:
        raise UnsupportedFileType(f"No parser for {ext}")
    return parser_cls()
