"""Turn an uploaded file into clean text sections. Content is data: it is never executed."""
from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
import socket
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

MAX_PAGES = 2000
MAX_CHARS = 2_000_000
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "csv", "json"}


class IngestionError(ValueError):
    """A problem the person uploading can fix. The message is shown to them."""


@dataclass(frozen=True)
class Section:
    title: str
    text: str


_CONTROL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-​⁠﻿]")
_SPACES = re.compile(r"[ \t ]+")
_BLANKS = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise Unicode and whitespace. Zero-width joiners stay: Bengali and Hindi need them."""
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = _SPACES.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip()


def detect_type(filename: str, data: bytes) -> str:
    """Check the extension against the file's first bytes, so a renamed file is refused."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise IngestionError("Choose a PDF, DOCX, TXT, CSV or JSON file.")
    if not data:
        raise IngestionError("The file is empty.")
    if extension == "pdf" and not data.startswith(b"%PDF-"):
        raise IngestionError("This file does not look like a PDF.")
    if extension == "docx" and not data.startswith(b"PK\x03\x04"):
        raise IngestionError("This file does not look like a Word document.")
    if extension in ("txt", "md", "csv", "json") and b"\x00" in data[:4096]:
        raise IngestionError("This file does not look like text.")
    return "txt" if extension == "md" else extension


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise IngestionError("Save the file as UTF-8 and try again.")


def parse_pdf(data: bytes) -> list[Section]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestionError("Remove the password from this PDF and try again.")
        if len(reader.pages) > MAX_PAGES:
            raise IngestionError(f"This PDF has more than {MAX_PAGES:,} pages.")
        sections = []
        for number, page in enumerate(reader.pages, start=1):
            text = clean_text(page.extract_text() or "")
            if text:
                sections.append(Section(f"Page {number}", text))
    except PyPdfError as error:
        raise IngestionError("This PDF could not be read.") from error
    if not sections:
        raise IngestionError("No text found. Scanned PDFs need OCR before upload.")
    return sections


def parse_docx(data: bytes) -> list[Section]:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as error:  # python-docx raises many unrelated types on bad files
        raise IngestionError("This Word document could not be read.") from error
    sections: list[Section] = []
    heading = "Document"
    buffer: list[str] = []

    def flush() -> None:
        text = clean_text("\n".join(buffer))
        if text:
            sections.append(Section(heading, text))
        buffer.clear()

    for paragraph in document.paragraphs:
        if paragraph.style is not None and (paragraph.style.name or "").startswith("Heading"):
            flush()
            heading = paragraph.text.strip() or heading
        elif paragraph.text.strip():
            buffer.append(paragraph.text)
    flush()
    for index, table in enumerate(document.tables, start=1):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        text = clean_text("\n".join(rows))
        if text:
            sections.append(Section(f"Table {index}", text))
    if not sections:
        raise IngestionError("No text found in this Word document.")
    return sections


def _heading(line: str) -> str:
    """The heading on this line, or nothing. A heading is short and does not end like a sentence."""
    if line.startswith("#"):
        return line.lstrip("# ").strip()
    if len(line) <= 60 and not line.endswith((".", "।", "॥", "?", "!", ":", ";", ",")):
        return line
    return ""


def parse_txt(data: bytes) -> list[Section]:
    text = clean_text(_decode(data))
    if not text:
        raise IngestionError("The file has no text.")
    sections: list[Section] = []
    title = "Document"
    body: list[str] = []

    def flush() -> None:
        if body:
            sections.append(Section(title, "\n".join(body)))
            body.clear()

    for block in text.split("\n\n"):
        lines = block.split("\n")
        found = _heading(lines[0]) if len(lines) > 1 or lines[0].startswith("#") else ""
        if found:
            flush()
            title = found
            lines = lines[1:]
        body.extend(lines)
    flush()
    return sections or [Section("Document", text)]


def parse_csv(data: bytes) -> list[Section]:
    reader = csv.DictReader(io.StringIO(_decode(data)))
    if not reader.fieldnames:
        raise IngestionError("The CSV needs a header row.")
    sections = []
    for number, row in enumerate(reader, start=2):
        parts = [f"{key}: {value}" for key, value in row.items() if key and value and str(value).strip()]
        if parts:
            sections.append(Section(f"Row {number}", clean_text("\n".join(parts))))
    if not sections:
        raise IngestionError("The CSV has no data rows.")
    return sections


def _faq_item(item: dict) -> Section | None:
    lowered = {str(key).lower(): value for key, value in item.items()}
    question = lowered.get("question") or lowered.get("q")
    answer = lowered.get("answer") or lowered.get("a")
    if question and answer:
        return Section(str(question)[:200], clean_text(f"{question}\n{answer}"))
    return None


def parse_json(data: bytes) -> list[Section]:
    try:
        parsed = json.loads(_decode(data))
    except json.JSONDecodeError as error:
        raise IngestionError("This JSON file is not valid.") from error

    def flatten(value: object, path: str = "") -> list[str]:
        if isinstance(value, dict):
            return [line for key, item in value.items() for line in flatten(item, f"{path}{key}: ")]
        if isinstance(value, list):
            return [line for item in value for line in flatten(item, path)]
        return [f"{path}{value}"] if value not in (None, "") else []

    items = parsed if isinstance(parsed, list) else [parsed]
    sections: list[Section] = []
    for index, item in enumerate(items, start=1):
        faq = _faq_item(item) if isinstance(item, dict) else None
        if faq:
            sections.append(faq)
            continue
        text = clean_text("\n".join(flatten(item)))
        if text:
            sections.append(Section(f"Item {index}", text))
    if not sections:
        raise IngestionError("The JSON file has no text.")
    return sections


def parse_bytes(filename: str, data: bytes) -> tuple[str, list[Section]]:
    kind = detect_type(filename, data)
    parser = {
        "pdf": parse_pdf,
        "docx": parse_docx,
        "txt": parse_txt,
        "csv": parse_csv,
        "json": parse_json,
    }[kind]
    sections = parser(data)
    if sum(len(section.text) for section in sections) > MAX_CHARS:
        raise IngestionError("This document is too long. Split it into smaller files.")
    return kind, sections


def parse_faq(pairs: list[dict]) -> list[Section]:
    sections = [section for section in (_faq_item(pair) for pair in pairs) if section]
    if not sections:
        raise IngestionError("Add at least one question and answer.")
    return sections


def check_public_url(url: str) -> None:
    """Refuse addresses inside the network, so a pasted URL cannot reach internal services."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise IngestionError("Enter a full web address that starts with https://.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as error:
        raise IngestionError("This web address could not be found.") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise IngestionError("This web address points to a private network.")


def parse_html(html: str) -> list[Section]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "form", "iframe", "svg"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else "Web page"
    text = clean_text(soup.get_text("\n"))
    if len(text) < 40:
        raise IngestionError("No readable text found on this page.")
    return [Section(title[:200], text)]


async def fetch_url(url: str, max_bytes: int) -> list[Section]:
    import httpx

    check_public_url(url)
    limits = httpx.Timeout(15.0)
    async with httpx.AsyncClient(follow_redirects=False, timeout=limits) as client:
        current = url
        for _ in range(4):  # each redirect target is checked again
            async with client.stream("GET", current, headers={"User-Agent": "voice-agent-platform"}) as response:
                if response.is_redirect:
                    current = str(response.url.join(response.headers.get("location", "")))
                    check_public_url(current)
                    continue
                if response.status_code >= 400:
                    raise IngestionError(f"The page returned error {response.status_code}.")
                if "html" not in response.headers.get("content-type", "") and "text" not in response.headers.get(
                    "content-type", ""
                ):
                    raise IngestionError("This address is not a web page.")
                body = bytearray()
                async for block in response.aiter_bytes():
                    body.extend(block)
                    if len(body) > max_bytes:
                        raise IngestionError("This page is too large.")
                return parse_html(body.decode(response.encoding or "utf-8", errors="replace"))
    raise IngestionError("This address redirects too many times.")
