"""Bounded parser port and adapters for supported enterprise file types."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from bs4 import BeautifulSoup
from docx import Document
from markdown_it import MarkdownIt
from pypdf import PdfReader


class ParsingFailed(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    paragraphs: tuple[str, ...]
    language: str


class Parser(Protocol):
    def parse(self, content: bytes) -> ParsedDocument: ...


def _normalize(parts: list[str]) -> ParsedDocument:
    paragraphs = tuple(" ".join(part.split()) for part in parts if part and part.strip())
    if not paragraphs:
        raise ParsingFailed("NO_EXTRACTABLE_TEXT")
    joined = "".join(paragraphs)
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in joined)
    return ParsedDocument(paragraphs=paragraphs, language="zh" if cjk else "en")


class TextParser:
    def parse(self, content: bytes) -> ParsedDocument:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParsingFailed("TEXT_ENCODING_UNSUPPORTED") from exc
        return _normalize(text.splitlines())


class MarkdownParser:
    def parse(self, content: bytes) -> ParsedDocument:
        try:
            rendered = MarkdownIt().render(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ParsingFailed("TEXT_ENCODING_UNSUPPORTED") from exc
        return _normalize(BeautifulSoup(rendered, "html.parser").get_text("\n").splitlines())


class HtmlParser:
    def parse(self, content: bytes) -> ParsedDocument:
        soup = BeautifulSoup(content, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        return _normalize(soup.get_text("\n").splitlines())


class PdfParser:
    def parse(self, content: bytes) -> ParsedDocument:
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ParsingFailed("ENCRYPTED_FILE")
            return _normalize([page.extract_text() or "" for page in reader.pages])
        except ParsingFailed:
            raise
        except Exception as exc:
            raise ParsingFailed("PDF_PARSE_FAILED") from exc


class DocxParser:
    def parse(self, content: bytes) -> ParsedDocument:
        try:
            document = Document(BytesIO(content))
            return _normalize([paragraph.text for paragraph in document.paragraphs])
        except Exception as exc:
            raise ParsingFailed("DOCX_PARSE_FAILED") from exc


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {
            "text/plain": TextParser(),
            "text/markdown": MarkdownParser(),
            "text/html": HtmlParser(),
            "application/pdf": PdfParser(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
                DocxParser()
            ),
        }

    def parse(self, media_type: str, content: bytes) -> ParsedDocument:
        try:
            parser = self._parsers[media_type]
        except KeyError as exc:
            raise ParsingFailed("UNSUPPORTED_MEDIA_TYPE") from exc
        return parser.parse(content)
