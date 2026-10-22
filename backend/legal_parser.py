"""Bộ phân tích cấu trúc văn bản pháp luật Việt Nam (tất định, không dùng LLM).

Văn bản  ->  Chương  ->  Điều  ->  Khoản  ->  Điểm

Module này được dùng bởi:
- ingest.py       : cắt chunk theo Điều/Khoản kèm ngữ cảnh phân cấp (khối Neural)
- graph_ingest.py : làm "khung xương" cho đồ thị tri thức và đối chiếu kết quả LLM (khối Symbolic)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader

# ---------------------------------------------------------------------------
# Danh mục văn bản trong kho dữ liệu (nhận diện theo tên file, fallback regex)
# ---------------------------------------------------------------------------
CYBERCRIME_ARTICLES = {
    12, 14, 155, 156, 159,
    285, 286, 287, 288, 289, 290, 291, 292, 293, 294,
    331,
}

DOCUMENT_REGISTRY: list[dict[str, Any]] = [
    {
        "pattern": r"15-2020",
        "code": "15/2020/NĐ-CP",
        "title": "Nghị định 15/2020/NĐ-CP quy định xử phạt vi phạm hành chính trong lĩnh vực "
        "bưu chính, viễn thông, tần số vô tuyến điện, công nghệ thông tin và giao dịch điện tử",
        "short": "Nghị định 15/2020/NĐ-CP",
        "type": "DECREE",
    },
    {
        "pattern": r"24-2018",
        "code": "24/2018/QH14",
        "title": "Luật An ninh mạng 2018 (Luật số 24/2018/QH14)",
        "short": "Luật An ninh mạng 2018",
        "type": "LAW",
    },
    {
        "pattern": r"67-2006",
        "code": "67/2006/QH11",
        "title": "Luật Công nghệ thông tin 2006 (Luật số 67/2006/QH11)",
        "short": "Luật Công nghệ thông tin 2006",
        "type": "LAW",
    },
    {
        "pattern": r"luat20-2023|20-2023-qh15",
        "code": "20/2023/QH15",
        "title": "Luật Giao dịch điện tử 2023 (Luật số 20/2023/QH15)",
        "short": "Luật Giao dịch điện tử 2023",
        "type": "LAW",
    },
    {
        "pattern": r"^luat24\.pdf$|24-2023-qh15",
        "code": "24/2023/QH15",
        "title": "Luật Viễn thông 2023 (Luật số 24/2023/QH15)",
        "short": "Luật Viễn thông 2023",
        "type": "LAW",
    },
    {
        "pattern": r"^luat60\.pdf$|60-2024-qh15",
        "code": "60/2024/QH15",
        "title": "Luật Dữ liệu 2024 (Luật số 60/2024/QH15)",
        "short": "Luật Dữ liệu 2024",
        "type": "LAW",
    },
    {
        "pattern": r"07-2022-qh15",
        "code": "07/2022/QH15",
        "title": "Luật sửa đổi, bổ sung một số điều của Luật Sở hữu trí tuệ 2022 (Luật số 07/2022/QH15)",
        "short": "Luật SHTT sửa đổi 2022",
        "type": "LAW",
    },
    {
        "pattern": r"19-2023-QH15",
        "code": "19/2023/QH15",
        "title": "Luật Bảo vệ quyền lợi người tiêu dùng 2023 (Luật số 19/2023/QH15)",
        "short": "Luật Bảo vệ quyền lợi NTD 2023",
        "type": "LAW",
    },
    {
        "pattern": r"422009qh12|62-VBHN-VPQH",
        "code": "42/2009/QH12",
        "title": "Luật Tần số vô tuyến điện 2009 (Văn bản hợp nhất 62/VBHN-VPQH)",
        "short": "Luật Tần số vô tuyến điện",
        "type": "LAW",
    },
    {
        "pattern": r"26_2026_VBHN",
        "code": "26/2026/VBHN-BKHCN",
        "title": "Nghị định hợp nhất 26/2026/VBHN-NĐ-BKHCN quy định chi tiết Luật Tần số vô tuyến điện",
        "short": "VBHN 26/2026/VBHN-BKHCN",
        "type": "DECREE",
    },
    {
        "pattern": r"20-2026-QH16",
        "code": "20/2026/QH16",
        "title": "Luật số 20/2026/QH16 sửa đổi Luật Tần số vô tuyến điện, Luật Viễn thông, Luật Giao dịch điện tử",
        "short": "Luật sửa đổi Viễn thông & GDĐT 2026",
        "type": "LAW",
    },
    {
        "pattern": r"100-2015-QH13",
        "code": "100/2015/QH13",
        "title": "Bộ luật Hình sự 2015 - Sửa đổi, bổ sung 2017 (Nhóm tội phạm CNTT & Mạng viễn thông)",
        "short": "Bộ luật Hình sự 2015",
        "type": "CRIMINAL_CODE",
        "article_filter": CYBERCRIME_ARTICLES,
    },
]

POINT_LETTERS = "abcdđeghiklmnopqrstuvxy"  # thứ tự điểm trong văn bản pháp luật Việt Nam

_HEADER_RE = re.compile(r"(?m)^\s*\d*\s*CÔNG BÁO\s*/\s*Số[^\n]*$")
_ARTICLE_RE = re.compile(r"(?m)^[ \t]*Điều[ \t]+(\d+)[ \t]*\.[ \t]*(.*)$")
_CHAPTER_RE = re.compile(r"(?m)^[ \t]*Chương[ \t]+([IVXLC]+)[ \t]*$")
_CLAUSE_RE = re.compile(r"(?m)^[ \t]*(\d{1,2})\.[ \t]+")
_POINT_RE = re.compile(r"(?m)^[ \t]*([a-zđ])\)[ \t]+")
_ARTICLE_REF_RE = re.compile(r"Điều\s+(\d{1,3})(?!\s*\d)")

_FINE_RE = re.compile(
    r"Ph\s*ạt\s+ti\s*ền\s+t\s*ừ\s+([\d.\s]+?)\s*đồng\s+đến\s+([\d.\s]+?)\s*đồng",
    re.IGNORECASE,
)
_WARNING_RE = re.compile(r"Ph\s*ạt\s+c\s*ảnh\s+cáo", re.IGNORECASE)

# Sửa lỗi pypdf chèn khoảng trắng giữa âm tiết: "Ph ạt ti ền t ừ" -> "Phạt tiền từ"
_VOWELS = "aàáảãạăằắẳẵặâầấẩẫậeèéẻẽẹêềếểễệiìíỉĩịoòóỏõọôồốổỗộơờớởỡợuùúủũụưừứửữựyỳýỷỹỵ"
_MARKED_VOWELS = "".join(ch for ch in _VOWELS if ch not in "aeiouy")
_MARKED_VOWELS += _MARKED_VOWELS.upper()
_E_FAMILY = "êềếểễệÊỀẾỂỄỆ"
_CONSONANT_ONLY_SPLIT = re.compile(
    rf"(?<![^\W\d_])([bcdđghklmnpqrstvxBCDĐGHKLMNPQRSTVX]{{1,3}}|[gG]i|[qQ]u) (?=[{_MARKED_VOWELS}])"
)
_VOWEL_E_SPLIT = re.compile(rf"(?<=[iyuoIYUO]) (?=[{_E_FAMILY}])")


def normalize_text(text: str) -> str:
    """Chuẩn hóa Unicode + sửa phần lớn lỗi tách âm tiết do trích xuất PDF."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = _CONSONANT_ONLY_SPLIT.sub(r"\1", text)
    text = _VOWEL_E_SPLIT.sub("", text)
    text = re.sub(r" +\n", "\n", text)
    return text


def parse_amount(raw: str) -> int | None:
    digits = re.sub(r"[^\d]", "", raw or "")
    return int(digits) if digits else None


# ---------------------------------------------------------------------------
# Mô hình dữ liệu
# ---------------------------------------------------------------------------
@dataclass
class Point:
    letter: str
    text: str


@dataclass
class Clause:
    number: int
    text: str
    points: list[Point] = field(default_factory=list)
    fine_min: int | None = None
    fine_max: int | None = None
    warning: bool = False


@dataclass
class Article:
    doc_code: str
    number: int
    title: str
    chapter: str
    text: str
    source: str
    page: int
    clauses: list[Clause] = field(default_factory=list)
    references: list[int] = field(default_factory=list)

    @property
    def id(self) -> str:
        return article_id(self.doc_code, self.number)

    def heading(self) -> str:
        return f"Điều {self.number}. {self.title}".strip()


@dataclass
class LegalDocument:
    code: str
    title: str
    short: str
    doc_type: str
    sources: list[str] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)


def article_id(doc_code: str, number: int) -> str:
    return f"{doc_code}:Điều {number}"


def clause_id(doc_code: str, article_number: int, clause_number: int) -> str:
    return f"{article_id(doc_code, article_number)}:Khoản {clause_number}"


# ---------------------------------------------------------------------------
# Phân tích
# ---------------------------------------------------------------------------
def _identify_document(pdf: Path, first_page: str) -> dict[str, Any]:
    for entry in DOCUMENT_REGISTRY:
        if re.search(entry["pattern"], pdf.name, re.IGNORECASE):
            return entry
    match = re.search(r"(?:Luật\s+)?Số\s*:\s*(\d+/\d{4}/[A-ZĐ0-9\-]+)", first_page, re.IGNORECASE)
    code = match.group(1).upper() if match else pdf.stem
    return {"code": code, "title": code, "short": code, "type": "OTHER"}


def _read_pages(pdf: Path) -> list[str]:
    reader = PdfReader(str(pdf))
    pages = []
    for page in reader.pages:
        text = normalize_text(page.extract_text() or "")
        pages.append(_HEADER_RE.sub("", text))
    return pages


def _sequential_matches(pattern: re.Pattern, text: str, keys: list[str]):
    """Chỉ nhận các mốc Khoản/Điểm xuất hiện đúng thứ tự (1,2,3... hoặc a,b,c...)."""
    accepted = []
    expected = 0
    for match in pattern.finditer(text):
        if expected < len(keys) and match.group(1) == keys[expected]:
            accepted.append(match)
            expected += 1
    return accepted


def _split_points(clause_text: str) -> list[Point]:
    matches = _sequential_matches(_POINT_RE, clause_text, list(POINT_LETTERS))
    points = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(clause_text)
        body = " ".join(clause_text[match.end() : end].split())
        points.append(Point(letter=match.group(1), text=body))
    return points


def _split_clauses(body: str, parse_fines: bool = True) -> list[Clause]:
    matches = _sequential_matches(_CLAUSE_RE, body, [str(i) for i in range(1, 100)])
    clauses = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        raw = body[match.end() : end].strip()
        flat = " ".join(raw.split())
        clause = Clause(number=int(match.group(1)), text=flat, points=_split_points(raw))
        if parse_fines:
            fine = _FINE_RE.search(flat[:400])
            if fine:
                clause.fine_min = parse_amount(fine.group(1))
                clause.fine_max = parse_amount(fine.group(2))
            clause.warning = bool(_WARNING_RE.search(flat[:200]))
        clauses.append(clause)
    return clauses


def _parse_articles(meta: dict[str, Any], pdf: Path, pages: list[str], last_number: int) -> list[Article]:
    offsets, chunks, cursor = [], [], 0
    for page_text in pages:
        offsets.append(cursor)
        chunks.append(page_text)
        cursor += len(page_text) + 1
    full = "\n".join(chunks)

    def page_of(position: int) -> int:
        page = 0
        for index, start in enumerate(offsets):
            if start <= position:
                page = index
        return page + 1

    chapters = [(m.start(), m.group(1)) for m in _CHAPTER_RE.finditer(full)]
    headers = []
    for match in _ARTICLE_RE.finditer(full):
        number = int(match.group(1))
        if number <= last_number:
            continue  # bỏ trích dẫn "Điều x." trong thân văn bản / tham chiếu ngược
        headers.append(match)
        last_number = number

    article_filter: set[int] | None = meta.get("article_filter")
    parse_fines = meta.get("type") != "CRIMINAL_CODE"

    articles = []
    for index, match in enumerate(headers):
        number = int(match.group(1))
        if article_filter is not None and number not in article_filter:
            continue
        start = match.start()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(full)
        # Cắt bỏ tiêu đề Chương tiếp theo nằm trong khoảng của Điều hiện tại
        for chapter_pos, _ in chapters:
            if start < chapter_pos < end:
                end = chapter_pos
                break
        block = full[start:end].strip()
        lines = block.split("\n")
        title = match.group(2).strip()
        body_start = 1
        # Tiêu đề Điều có thể xuống dòng (dòng tiếp theo bắt đầu bằng chữ thường)
        while body_start < len(lines) and lines[body_start].strip()[:1].islower():
            title += " " + lines[body_start].strip()
            body_start += 1
        body = "\n".join(lines[body_start:])
        chapter = ""
        for chapter_pos, chapter_name in chapters:
            if chapter_pos < start:
                chapter = chapter_name
        refs = sorted(
            {int(r) for r in _ARTICLE_REF_RE.findall(body) if int(r) != number}
        )
        articles.append(
            Article(
                doc_code=meta["code"],
                number=number,
                title=" ".join(title.split()),
                chapter=chapter,
                text=" ".join(block.split()),
                source=pdf.name,
                page=page_of(start),
                clauses=_split_clauses(body, parse_fines=parse_fines),
                references=refs,
            )
        )
    return articles


def load_corpus(data_dir: Path, core_only: bool = False) -> list[LegalDocument]:
    """Đọc toàn bộ PDF trong data/, gộp các file thuộc cùng một văn bản (VD: 2 số Công báo),
    và tự động chọn bản đầy đủ/sạch nhất nếu có 2 file PDF trùng cùng một văn bản."""
    documents: dict[str, LegalDocument] = {}
    core_codes = {"15/2020/NĐ-CP", "24/2018/QH14", "67/2006/QH11"}

    for pdf in sorted(data_dir.glob("*.pdf")):
        pages = _read_pages(pdf)
        if sum(len(p.strip()) for p in pages) < 200:
            print(f"[PARSER] Bỏ qua {pdf.name}: PDF dạng ảnh scan, không có lớp văn bản (cần OCR).")
            continue
        meta = _identify_document(pdf, pages[0] if pages else "")
        if core_only and meta["code"] not in core_codes:
            continue
        document = documents.get(meta["code"])
        if document is None:
            document = LegalDocument(
                code=meta["code"],
                title=meta["title"],
                short=meta.get("short", meta["code"]),
                doc_type=meta["type"],
            )
            documents[meta["code"]] = document
            new_articles = _parse_articles(meta, pdf, pages, 0)
            document.sources.append(pdf.name)
            document.articles.extend(new_articles)
            print(f"[PARSER] {pdf.name}: {len(new_articles)} Điều -> {document.code}")
        else:
            last = document.articles[-1].number if document.articles else 0
            continued_articles = _parse_articles(meta, pdf, pages, last)
            if continued_articles:
                # Trường hợp văn bản tách làm 2 phần liên tiếp (VD: Nghị định 15/2020 phần 1 & 2)
                document.sources.append(pdf.name)
                document.articles.extend(continued_articles)
                print(f"[PARSER] {pdf.name}: +{len(continued_articles)} Điều (nối tiếp) -> {document.code}")
            else:
                # Trường hợp file thứ 2 là bản hợp nhất/bản trùng của cùng văn bản (bắt đầu lại từ Điều 1)
                alt_articles = _parse_articles(meta, pdf, pages, 0)
                if len(alt_articles) >= len(document.articles) and alt_articles:
                    document.sources = [pdf.name]
                    document.articles = alt_articles
                    print(
                        f"[PARSER] {pdf.name}: {len(alt_articles)} Điều (thay thế bản cũ ít Điều hơn) -> {document.code}"
                    )
                else:
                    print(f"[PARSER] Bỏ qua bản trùng {pdf.name} ({len(alt_articles)} Điều) -> đã có {document.code}")
    return list(documents.values())


if __name__ == "__main__":
    import sys

    from config import DATA_DIR

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for doc in load_corpus(DATA_DIR):
        fines = sum(1 for a in doc.articles for c in a.clauses if c.fine_min)
        print(f"{doc.code} ({doc.short}): {len(doc.articles)} Điều, {fines} khoản có khung phạt tiền")
        for art in doc.articles[:2]:
            print("  ", art.id, "|", art.heading(), "| trang", art.page, "| khoản:", len(art.clauses))
