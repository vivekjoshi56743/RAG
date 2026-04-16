import re


class MarkdownParser:
    """
    Extract text from Markdown files.
    Strips syntax, preserves semantic structure (headings become section boundaries).
    """

    def extract(self, file_bytes: bytes) -> list[dict]:
        text = file_bytes.decode("utf-8")

        # Strip markdown syntax, preserve readable text
        # text = re.sub(r'```[\s\S]*?```', '[code block]', text)
        text = re.sub(r'!\[.*?\]\(.*?\)', '[image]', text)
        text = re.sub(r'\[(.+?)\]\(.*?\)', r'\1', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)

        # Split at H1/H2 headers as natural section boundaries
        sections = re.split(r'\n(?=#{1,2}\s)', text)
        pages = []
        for section in sections:
            clean = re.sub(r'^#{1,6}\s+', '', section, flags=re.MULTILINE).strip()
            if clean:
                pages.append({"page": len(pages) + 1, "text": clean})

        return pages if pages else [{"page": 1, "text": text}]
