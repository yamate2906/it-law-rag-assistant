"""Bộ phân tích cấu trúc văn bản pháp luật Việt Nam (tất định, hỗ trợ PDF văn bản, PDF scan OCR, Ảnh, Word, Text).

Văn bản  ->  Chương  ->  Điều  ->  Khoản  ->  Điểm

Module này được dùng bởi:
- ingest.py       : cắt chunk theo Điều/Khoản kèm ngữ cảnh phân cấp (khối Neural)
- graph_ingest.py : làm "khung xương" cho đồ thị tri thức và đối chiếu kết quả LLM (khối Symbolic)

Tính năng tối ưu:
- Hỗ trợ đọc trực tiếp PDF có lớp text, PDF scan (ảnh trong PDF), file ảnh (.png, .jpg, .jpeg, .webp, .bmp, .tif, .tiff), Word (.docx), Text (.txt, .md).
- Tự động chạy OCR đa luồng (parallel Tesseract OCR) và lưu bộ nhớ đệm vĩnh viễn tại `data/.ocr_cache/` để không bao giờ phải OCR lại file đã đọc.
- Tự động fallback sang chia theo Trang/Mục nếu tài liệu là Công văn, Phụ lục hoặc ảnh tài liệu không chia theo "Điều X.".
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader

try:
    import pymupdf as fitz  # Dùng tên chuẩn pymupdf để không bị cảnh báo deprecated 'fitz'
except ImportError:
    try:
        import fitz  # type: ignore[no-redef]
    except ImportError:
        fitz = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from docx import Document as WordDocument
except ImportError:
    WordDocument = None

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

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
        "pattern": r"48-cp-kgvx",
        "code": "48/CP-KGVX",
        "title": "Công văn 48/CP-KGVX năm 2020 đính chính Nghị định 15/2020/NĐ-CP",
        "short": "Công văn 48/CP-KGVX (Đính chính NĐ 15/2020)",
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
        "pattern": r"luat116-2025",
        "code": "116/2025/QH15",
        "title": "Luật An ninh mạng 2025 (Luật số 116/2025/QH15)",
        "short": "Luật An ninh mạng 2025",
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
    {
        "pattern": r"^12\.signed\.pdf$",
        "code": "12/2017/QH14",
        "title": "Luật số 12/2017/QH14 sửa đổi, bổ sung một số điều của Bộ luật Hình sự số 100/2015/QH13",
        "short": "Luật sửa đổi BLHS 2017",
        "type": "CRIMINAL_CODE",
    },
    {
        "pattern": r"^13nd\.signed\.pdf$",
        "code": "13/2023/NĐ-CP",
        "title": "Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân",
        "short": "Nghị định 13/2023/NĐ-CP (Bảo vệ DLCN)",
        "type": "DECREE",
    },
    {
        "pattern": r"^147-nd\.signed\.pdf$",
        "code": "147/2024/NĐ-CP",
        "title": "Nghị định 147/2024/NĐ-CP quản lý, cung cấp, sử dụng dịch vụ Internet và thông tin trên mạng",
        "short": "Nghị định 147/2024/NĐ-CP (Internet & MXH)",
        "type": "DECREE",
    },
    {
        "pattern": r"^163nd\.signed\.pdf$",
        "code": "163/2024/NĐ-CP",
        "title": "Nghị định 163/2024/NĐ-CP quy định chi tiết một số điều và biện pháp thi hành Luật Viễn thông",
        "short": "Nghị định 163/2024/NĐ-CP (Hướng dẫn Luật Viễn thông)",
        "type": "DECREE",
    },
    {
        "pattern": r"^165nd\.signed\.pdf$",
        "code": "165/2025/NĐ-CP",
        "title": "Nghị định 165/2025/NĐ-CP quy định chi tiết một số điều và biện pháp thi hành Luật Dữ liệu",
        "short": "Nghị định 165/2025/NĐ-CP (Hướng dẫn Luật Dữ liệu)",
        "type": "DECREE",
    },
    {
        "pattern": r"^23-cp\.signed\.pdf$",
        "code": "23/2025/NĐ-CP",
        "title": "Nghị định 23/2025/NĐ-CP quy định về chữ ký điện tử và dịch vụ tin cậy",
        "short": "Nghị định 23/2025/NĐ-CP (Chữ ký điện tử)",
        "type": "DECREE",
    },
    {
        "pattern": r"^356-nd\.signed\.pdf$",
        "code": "356/2025/NĐ-CP",
        "title": "Nghị định 356/2025/NĐ-CP quy định chi tiết Luật Bảo vệ dữ liệu cá nhân",
        "short": "Nghị định 356/2025/NĐ-CP",
        "type": "DECREE",
    },
    {
        "pattern": r"^142-2026-ndcp\.signed\.pdf$",
        "code": "142/2026/NĐ-CP",
        "title": "Nghị định 142/2026/NĐ-CP quy định chi tiết thi hành Luật",
        "short": "Nghị định 142/2026/NĐ-CP",
        "type": "DECREE",
    },
    {
        "pattern": r"^224-ndcp\.signed\.pdf$",
        "code": "224/2026/NĐ-CP",
        "title": "Nghị định 224/2026/NĐ-CP quy định chi tiết một số điều và biện pháp thi hành Luật Chuyển đổi số",
        "short": "Nghị định 224/2026/NĐ-CP (Chuyển đổi số)",
        "type": "DECREE",
    },
    {
        "pattern": r"248-2026",
        "code": "248/2026/NĐ-CP",
        "title": "Nghị định 248/2026/NĐ-CP quy định chi tiết một số điều của Luật Thương mại điện tử",
        "short": "Nghị định 248/2026/NĐ-CP (Thương mại điện tử)",
        "type": "DECREE",
    },
    {
        "pattern": r"333_2026",
        "code": "333/2026/NĐ-CP",
        "title": "Nghị định 333/2026/NĐ-CP của Chính phủ",
        "short": "Nghị định 333/2026/NĐ-CP",
        "type": "DECREE",
    },
    {
        "pattern": r"^52-nd\.pdf$",
        "code": "52/2013/NĐ-CP",
        "title": "Nghị định 52/2013/NĐ-CP về thương mại điện tử",
        "short": "Nghị định 52/2013/NĐ-CP (TMĐT)",
        "type": "DECREE",
    },
    {
        "pattern": r"^85\.signed\.pdf$",
        "code": "85/2016/NĐ-CP",
        "title": "Nghị định 85/2016/NĐ-CP về bảo đảm an toàn hệ thống thông tin theo cấp độ",
        "short": "Nghị định 85/2016/NĐ-CP (An toàn HTTT)",
        "type": "DECREE",
    },
    {
        "pattern": r"^86\.signed\.pdf$",
        "code": "86/2015/QH13",
        "title": "Luật An toàn thông tin mạng 2015 (Luật số 86/2015/QH13)",
        "short": "Luật An toàn thông tin mạng 2015",
        "type": "LAW",
    },
    {
        "pattern": r"^71qh15\.signed\.pdf$",
        "code": "71/2025/QH15",
        "title": "Luật Công nghiệp công nghệ số 2025 (Luật số 71/2025/QH15)",
        "short": "Luật Công nghiệp công nghệ số 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^91qh\.signed\.pdf$",
        "code": "91/2025/QH15",
        "title": "Luật Bảo vệ dữ liệu cá nhân 2025 (Luật số 91/2025/QH15)",
        "short": "Luật Bảo vệ dữ liệu cá nhân 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^93qh\.signed\.pdf$",
        "code": "93/2025/QH15",
        "title": "Luật Khoa học, Công nghệ và Đổi mới sáng tạo 2025 (Luật số 93/2025/QH15)",
        "short": "Luật KH, CN và Đổi mới sáng tạo 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^luat122\.2025\.qh15\.pdf$",
        "code": "122/2025/QH15",
        "title": "Luật Thương mại điện tử 2025 (Luật số 122/2025/QH15)",
        "short": "Luật Thương mại điện tử 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^luatso133\.2025\.qh15\.pdf$",
        "code": "133/2025/QH15",
        "title": "Luật Công nghệ cao 2025 (Luật số 133/2025/QH15)",
        "short": "Luật Công nghệ cao 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^luat134\.signed\.pdf$",
        "code": "134/2025/QH15",
        "title": "Luật Trí tuệ nhân tạo 2025 (Luật số 134/2025/QH15)",
        "short": "Luật Trí tuệ nhân tạo 2025",
        "type": "LAW",
    },
    {
        "pattern": r"^91\.signed\.pdf$|^91_\.pdf$",
        "code": "91/2015/QH13",
        "title": "Bộ luật Dân sự 2015 (Luật số 91/2015/QH13)",
        "short": "Bộ luật Dân sự 2015",
        "type": "LAW",
    },
]

POINT_LETTERS = "abcdđeghiklmnopqrstuvxy"  # thứ tự điểm trong văn bản pháp luật Việt Nam

_HEADER_RE = re.compile(r"(?m)^\s*\d*\s*CÔNG BÁO\s*/\s*Số[^\n]*$")
# Hỗ trợ cả các biến thể dấu tiếng Việt do OCR nhận diện ("Điều", "Điêu", "Điệu", "Điểu", "ĐIỀU")
_ARTICLE_RE = re.compile(
    r"(?m)^[ \t]*(?:Điều|Điêu|Điệu|Điểu|ĐIỀU|ĐIÊU)[ \t]+(\d{1,3})[ \t]*[.:][ \t]*(.*)$"
)
_CHAPTER_RE = re.compile(r"(?m)^[ \t]*(?:Chương|CHƯƠNG)[ \t]+([IVXLC]+)[ \t]*$")
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
        return f"Điều {self.number}. {self.title}".strip() if self.number > 0 else self.title


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
# OCR & Cache cho PDF Scan và File Ảnh
# ---------------------------------------------------------------------------
def _configure_tesseract() -> str:
    if pytesseract is None or Image is None:
        raise RuntimeError("Cần cài Pillow và pytesseract để chạy OCR.")
    tesseract_exe = shutil.which("tesseract")
    if not tesseract_exe:
        installed_exe = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        tesseract_exe = str(installed_exe) if installed_exe.exists() else None
    if not tesseract_exe:
        raise RuntimeError("Chưa cài Tesseract OCR hoặc chưa thêm tesseract.exe vào PATH.")
    pytesseract.pytesseract.tesseract_cmd = str(tesseract_exe)
    local_tessdata = Path.home() / "AppData/Local/Tesseract-OCR/tessdata"
    if local_tessdata.exists():
        return f"--psm 6 --tessdata-dir {local_tessdata.as_posix()}"
    return "--psm 6"


def _ocr_cache_path(path: Path) -> Path:
    cache_dir = path.parent / ".ocr_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    stat = path.stat()
    fingerprint = hashlib.sha1(f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}".encode("utf-8")).hexdigest()[:12]
    safe_name = re.sub(r"[^\w\-.]", "_", path.name)
    return cache_dir / f"{safe_name}.{fingerprint}.json"


def _pil_from_pixmap(pixmap) -> Any:
    """Chuyển đổi PyMuPDF Pixmap sang PIL Image an toàn cho mọi không gian màu (Grayscale/RGB/CMYK)."""
    if pixmap.n == 1:
        return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    if pixmap.n == 3:
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    if pixmap.n == 4:
        return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples).convert("RGB")
    # Trường hợp khác: chuyển qua pixmap RGB của PyMuPDF
    rgb_pix = fitz.Pixmap(fitz.csRGB, pixmap)
    return Image.frombytes("RGB", (rgb_pix.width, rgb_pix.height), rgb_pix.samples)


def _read_pdf_pages(pdf: Path) -> list[str]:
    try:
        reader = PdfReader(str(pdf))
        pages = [normalize_text(page.extract_text() or "") for page in reader.pages]
        if sum(len(page.strip()) for page in pages) >= 200:
            return [_HEADER_RE.sub("", page) for page in pages]
    except Exception:
        pages = []

    # Kiểm tra bộ nhớ đệm OCR trên đĩa trước khi chạy Tesseract
    cache_file = _ocr_cache_path(pdf)
    if cache_file.exists():
        try:
            cached_pages = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached_pages, list) and cached_pages:
                return [_HEADER_RE.sub("", normalize_text(p)) for p in cached_pages]
        except Exception:
            pass

    if fitz is None:
        raise RuntimeError("PDF scan cần cài PyMuPDF (pymupdf) để render trang ảnh cho OCR.")
    ocr_config = _configure_tesseract()

    try:
        with fitz.open(pdf) as scanned:
            total_pages = len(scanned)
            print(f"[OCR] Đang nhận diện văn bản từ PDF scan: {pdf.name} ({total_pages} trang)...", flush=True)
            images = []
            for page in scanned:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), colorspace=fitz.csGRAY, alpha=False)
                images.append(_pil_from_pixmap(pixmap))

        def _ocr_single(img):
            return normalize_text(pytesseract.image_to_string(img, lang="vie+eng", config=ocr_config))

        workers = min(6, os.cpu_count() or 4)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            ocr_pages = list(pool.map(_ocr_single, images))

        try:
            cache_file.write_text(json.dumps(ocr_pages, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    except Exception as exc:
        raise RuntimeError(f"OCR thất bại cho {pdf.name}: {exc}") from exc

    return [_HEADER_RE.sub("", page) for page in ocr_pages]


def _read_image_file(image_path: Path) -> list[str]:
    """Đọc và OCR trực tiếp file ảnh (.png, .jpg, .jpeg, .webp, .bmp, .tif, .tiff)."""
    cache_file = _ocr_cache_path(image_path)
    if cache_file.exists():
        try:
            cached_pages = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached_pages, list) and cached_pages:
                return [_HEADER_RE.sub("", normalize_text(p)) for p in cached_pages]
        except Exception:
            pass

    ocr_config = _configure_tesseract()
    try:
        print(f"[OCR] Đang nhận diện văn bản từ file ảnh: {image_path.name}...", flush=True)
        with Image.open(image_path) as raw_img:
            pages_out: list[str] = []
            n_frames = getattr(raw_img, "n_frames", 1)
            for frame_idx in range(n_frames):
                if n_frames > 1:
                    raw_img.seek(frame_idx)
                rgb_img = raw_img.convert("RGB")
                text = pytesseract.image_to_string(rgb_img, lang="vie+eng", config=ocr_config)
                pages_out.append(normalize_text(text))
        try:
            cache_file.write_text(json.dumps(pages_out, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return [_HEADER_RE.sub("", p) for p in pages_out]
    except Exception as exc:
        raise RuntimeError(f"OCR ảnh thất bại cho {image_path.name}: {exc}") from exc


def _read_pages(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf_pages(path)
    if suffix in IMAGE_SUFFIXES:
        return _read_image_file(path)
    if suffix in {".txt", ".md"}:
        return [normalize_text(path.read_text(encoding="utf-8-sig", errors="replace"))]
    if suffix == ".docx":
        if WordDocument is None:
            raise RuntimeError("Thiếu python-docx; cài bằng: python -m pip install python-docx")
        document = WordDocument(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        return [normalize_text("\n".join(parts))]
    return []


# ---------------------------------------------------------------------------
# Phân tích cấu trúc Điều / Khoản / Điểm
# ---------------------------------------------------------------------------
def identify_document_by_name(pdf: Path | str) -> dict[str, Any] | None:
    name = pdf.name if isinstance(pdf, Path) else Path(str(pdf)).name
    for entry in DOCUMENT_REGISTRY:
        if re.search(entry["pattern"], name, re.IGNORECASE):
            return entry
    return None


def _identify_document(pdf: Path, first_page: str) -> dict[str, Any]:
    by_name = identify_document_by_name(pdf)
    if by_name is not None:
        return by_name
    match = re.search(r"(?:Luật\s+)?Số\s*:\s*(\d+/\d{4}/[A-ZĐ0-9\-]+)", first_page, re.IGNORECASE)
    code = match.group(1).upper() if match else pdf.stem
    return {"code": code, "title": code, "short": code, "type": "OTHER"}


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
    raw_matches = list(_ARTICLE_RE.finditer(full))
    article_filter: set[int] | None = meta.get("article_filter")

    headers = []
    for idx, match in enumerate(raw_matches):
        number = int(match.group(1))
        if number <= last_number:
            continue
        # Chống nhảy cóc số Điều do trích dẫn Điều của luật sửa đổi hoặc lỗi OCR (VD: Điều 1 nhảy vọt lên Điều 200 rồi quay lại Điều 2)
        if article_filter is None and last_number > 0 and (number - last_number) > 25:
            upcoming_numbers = [int(m.group(1)) for m in raw_matches[idx + 1 : idx + 8]]
            if any(last_number < u <= last_number + 10 for u in upcoming_numbers):
                continue
        headers.append(match)
        last_number = number

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


def _fallback_page_articles(meta: dict[str, Any], path: Path, pages: list[str], start_index: int = 1) -> list[Article]:
    """Khi tài liệu là Công văn, Phụ lục, Ảnh chụp hoặc PDF scan không bắt được cấu trúc 'Điều X.',
    tự động tạo các phân mục theo trang để đảm bảo không có file nào bị từ chối nạp."""
    articles: list[Article] = []
    for idx, page_text in enumerate(pages, start=1):
        clean_page = " ".join(page_text.split())
        if len(clean_page) < 20:
            continue
        art_num = start_index + len(articles)
        articles.append(
            Article(
                doc_code=meta["code"],
                number=art_num,
                title=f" Nội dung trang {idx} ({path.name})",
                chapter="",
                text=clean_page,
                source=path.name,
                page=idx,
                clauses=[],
                references=sorted({int(r) for r in _ARTICLE_REF_RE.findall(clean_page)}),
            )
        )
    return articles


def load_corpus(
    data_dir: Path,
    core_only: bool = False,
    skip_sources: set[str] | None = None,
    only_sources: set[str] | None = None,
) -> list[LegalDocument]:
    """Đọc tài liệu trong data/, hỗ trợ bỏ qua các file đã nạp (skip_sources) để tiết kiệm thời gian và token."""
    documents: dict[str, LegalDocument] = {}
    core_codes = {"15/2020/NĐ-CP", "24/2018/QH14", "67/2006/QH11"}
    skip_set = skip_sources or set()

    files = sorted(
        path
        for path in data_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    for pdf in files:
        if only_sources is not None and pdf.name not in only_sources:
            continue
        if pdf.name in skip_set:
            print(f"⏭️ [SKIP] {pdf.name}: Đã nạp vào hệ thống trước đó -> Bỏ qua, không đọc/OCR lại.")
            continue

        known_meta = identify_document_by_name(pdf)
        if core_only and known_meta is not None and known_meta["code"] not in core_codes:
            continue

        try:
            pages = _read_pages(pdf)
        except Exception as exc:
            print(f"[PARSER] Bỏ qua {pdf.name}: {exc}")
            continue

        total_chars = sum(len(p.strip()) for p in pages)
        if total_chars < 30:
            print(f"[PARSER] Bỏ qua {pdf.name}: File rỗng hoặc không có chữ ({total_chars} ký tự).")
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
                doc_type=meta.get("type", "OTHER"),
            )
            documents[meta["code"]] = document
            new_articles = _parse_articles(meta, pdf, pages, 0)
            if not new_articles and meta.get("article_filter") is None:
                new_articles = _fallback_page_articles(meta, pdf, pages, start_index=1)
                print(
                    f"[PARSER] {pdf.name}: Không chia theo Điều -> Đã nạp theo {len(new_articles)} trang nội dung -> {document.code}"
                )
            else:
                print(f"[PARSER] {pdf.name}: {len(new_articles)} Điều -> {document.code}")
            document.sources.append(pdf.name)
            document.articles.extend(new_articles)
        else:
            last = document.articles[-1].number if document.articles else 0
            continued_articles = _parse_articles(meta, pdf, pages, last)
            if continued_articles:
                document.sources.append(pdf.name)
                document.articles.extend(continued_articles)
                print(f"[PARSER] {pdf.name}: +{len(continued_articles)} Điều (nối tiếp) -> {document.code}")
            else:
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
