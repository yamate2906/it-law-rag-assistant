"""Bộ suy luận luật tất định (Deterministic Legal Rule Engine) - linh hồn của khối Symbolic.

Nguyên tắc: LLM KHÔNG được tự tính toán số tiền. Mọi phép tính mức phạt theo chủ thể,
độ tuổi, mức trần... được thực hiện bằng Python thuần và trả về kèm "dấu vết suy luận"
(rule trace) có căn cứ pháp lý để hiển thị lên giao diện.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

ORGANIZATION = "ORGANIZATION"
INDIVIDUAL = "INDIVIDUAL"
SUBJECT_LABELS = {ORGANIZATION: "Tổ chức", INDIVIDUAL: "Cá nhân"}

# ---------------------------------------------------------------------------
# Tri thức luật cứng - trích nguyên văn từ kho dữ liệu (data/*.pdf)
# ---------------------------------------------------------------------------
DECREE_RULES: dict[str, dict] = {
    "15/2020/NĐ-CP": {
        # Điều 4 khoản 3: "Mức phạt tiền quy định từ Chương II đến Chương VII tại Nghị định này
        # được áp dụng đối với hành vi vi phạm hành chính của tổ chức, trừ quy định tại Điều 106
        # Nghị định này. Trường hợp cá nhân có hành vi vi phạm như của tổ chức thì mức phạt tiền
        # bằng 1/2 mức phạt tiền đối với tổ chức."
        "scope": (5, 119),  # Chương II (Điều 5) -> Chương VII (Điều 113-119, bao phủ Điều 114 & 114a theo NĐ 211/2025)
        "base_subject": ORGANIZATION,
        "individual_ratio": 0.5,
        "individual_base_articles": {106},  # Điều 106: vi phạm của người chơi (cá nhân)
        "basis": "Điều 4 khoản 3 Nghị định 15/2020/NĐ-CP",
        # Điều 4 khoản 1, 2: mức phạt tiền tối đa đối với cá nhân theo lĩnh vực
        "individual_caps": [
            ((5, 14), 40_000_000, "bưu chính"),
            ((15, 56), 100_000_000, "viễn thông"),
            ((57, 73), 100_000_000, "tần số vô tuyến điện"),
            ((74, 106), 100_000_000, "công nghệ thông tin"),
            ((107, 112), 40_000_000, "giao dịch điện tử"),
            ((113, 119), 100_000_000, "an toàn thông tin mạng, mật mã dân sự"),
        ],
        "cap_basis": "Điều 4 khoản 1, 2 Nghị định 15/2020/NĐ-CP",
    },
    "174/2026/NĐ-CP": {
        "scope": (5, 117),
        "base_subject": ORGANIZATION,
        "individual_ratio": 0.5,
        "individual_base_articles": {106},
        "basis": "Điều 4 khoản 3 Nghị định 174/2026/NĐ-CP",
        "individual_caps": [
            ((5, 117), 100_000_000, "lĩnh vực bưu chính, viễn thông, CNTT, giao dịch điện tử"),
        ],
        "cap_basis": "Điều 4 Nghị định 174/2026/NĐ-CP",
    },
    "330/2026/NĐ-CP": {
        "scope": (5, 95),
        "base_subject": ORGANIZATION,
        "individual_ratio": 0.5,
        "individual_base_articles": set(),
        "basis": "Điều 4 khoản 3 Nghị định 330/2026/NĐ-CP",
        "individual_caps": [
            ((5, 95), 100_000_000, "lĩnh vực an ninh mạng"),
        ],
        "cap_basis": "Điều 4 Nghị định 330/2026/NĐ-CP",
    },
}

VALID_DOC_CODES = {
    "15/2020/NĐ-CP",
    "174/2026/NĐ-CP",
    "330/2026/NĐ-CP",
    "14/2022/NĐ-CP",
    "211/2025/NĐ-CP",
    "24/2018/QH14",
    "67/2006/QH11",
    "20/2023/QH15",
    "24/2023/QH15",
    "60/2024/QH15",
    "07/2022/QH15",
    "19/2023/QH15",
    "42/2009/QH12",
    "26/2026/VBHN-BKHCN",
    "20/2026/QH16",
    "100/2015/QH13",
    # Các văn bản PDF scan trong kho dữ liệu data/
    "12/2017/QH14",
    "91/2015/QH13",
    "86/2015/QH13",
    "71/2025/QH15",
    "91/2025/QH15",
    "93/2025/QH15",
    "116/2025/QH15",
    "122/2025/QH15",
    "133/2025/QH15",
    "134/2025/QH15",
    "13/2023/NĐ-CP",
    "147/2024/NĐ-CP",
    "163/2024/NĐ-CP",
    "165/2025/NĐ-CP",
    "23/2025/NĐ-CP",
    "356/2025/NĐ-CP",
    "142/2026/NĐ-CP",
    "224/2026/NĐ-CP",
    "248/2026/NĐ-CP",
    "333/2026/NĐ-CP",
    "52/2013/NĐ-CP",
    "85/2016/NĐ-CP",
    "48/CP-KGVX",
}

# These known instruments are outside the corpus's subject area. Unknown codes
# are reported as unavailable in the corpus, never classified as nonexistent.
OUT_OF_SCOPE_DOC_CODES = {
    "100/2019/NĐ-CP": "Nghị định 100/2019/NĐ-CP (giao thông đường bộ)",
}
OUT_OF_SCOPE_DECREE_NUMBERS = {100}

KNOWN_DECREE_NUMBERS: dict[int, str] = {
    15: "15/2020/NĐ-CP",
    174: "174/2026/NĐ-CP",
    330: "330/2026/NĐ-CP",
    14: "14/2022/NĐ-CP",
    26: "26/2026/VBHN-BKHCN",
    13: "13/2023/NĐ-CP",
    23: "23/2025/NĐ-CP",
    52: "52/2013/NĐ-CP",
    85: "85/2016/NĐ-CP",
    142: "142/2026/NĐ-CP",
    147: "147/2024/NĐ-CP",
    163: "163/2024/NĐ-CP",
    165: "165/2025/NĐ-CP",
    211: "211/2025/NĐ-CP",
    224: "224/2026/NĐ-CP",
    248: "248/2026/NĐ-CP",
    333: "333/2026/NĐ-CP",
    356: "356/2025/NĐ-CP",
}

LAW_NAME_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"luật\s+an\s+ninh\s+mạng\s*2025", re.IGNORECASE), "116/2025/QH15"),
    (re.compile(r"luật\s+an\s+ninh\s+mạng\s*2018", re.IGNORECASE), "24/2018/QH14"),
    (re.compile(r"luật\s+an\s+ninh\s+mạng(?!\s*(?:2018|2025))", re.IGNORECASE), "116/2025/QH15"),
    (re.compile(r"luật\s+an\s+toàn\s+thông\s+tin\s+mạng", re.IGNORECASE), "86/2015/QH13"),
    (re.compile(r"luật\s+(?:công\s+nghệ\s+thông\s+tin|cntt)", re.IGNORECASE), "67/2006/QH11"),
    (re.compile(r"luật\s+giao\s+dịch\s+điện\s+tử", re.IGNORECASE), "20/2023/QH15"),
    (re.compile(r"luật\s+viễn\s+thông", re.IGNORECASE), "24/2023/QH15"),
    (re.compile(r"luật\s+dữ\s+liệu(?!\s+cá\s+nhân)", re.IGNORECASE), "60/2024/QH15"),
    (re.compile(r"luật\s+bảo\s+vệ\s+dữ\s+liệu\s+cá\s+nhân", re.IGNORECASE), "91/2025/QH15"),
    (re.compile(r"luật\s+công\s+nghiệp\s+công\s+nghệ\s+số", re.IGNORECASE), "71/2025/QH15"),
    (re.compile(r"luật\s+trí\s+tuệ\s+nhân\s+tạo", re.IGNORECASE), "134/2025/QH15"),
    (re.compile(r"luật\s+công\s+nghệ\s+cao", re.IGNORECASE), "133/2025/QH15"),
    (re.compile(r"luật\s+khoa\s+học\s*,?\s*công\s+nghệ", re.IGNORECASE), "93/2025/QH15"),
    (re.compile(r"luật\s+thương\s+mại\s+điện\s+tử", re.IGNORECASE), "122/2025/QH15"),
    (re.compile(r"luật\s+sở\s+hữu\s+trí\s+tuệ", re.IGNORECASE), "07/2022/QH15"),
    (re.compile(r"luật\s+bảo\s+vệ\s+quyền\s+lợi\s+người\s+tiêu\s+dùng", re.IGNORECASE), "19/2023/QH15"),
    (re.compile(r"luật\s+tần\s+số\s+vô\s+tuyến\s+điện", re.IGNORECASE), "42/2009/QH12"),
    (re.compile(r"luật\s+(?:số\s+)?20/2026/QH16|luật\s+sửa\s+đổi(?:,\s*bổ\s+sung)?\s+(?:một\s+số\s+điều\s+của\s+)?luật\s+tần\s+số", re.IGNORECASE), "20/2026/QH16"),
    (re.compile(r"nghị\s+định\s+(?:số\s+)?248/2026", re.IGNORECASE), "248/2026/NĐ-CP"),
    (re.compile(r"bộ\s+luật\s+hình\s+sự", re.IGNORECASE), "100/2015/QH13"),
    (re.compile(r"bộ\s+luật\s+dân\s+sự", re.IGNORECASE), "91/2015/QH13"),
]

# Quy tắc độ tuổi - Luật Xử lý vi phạm hành chính 2012 (sửa đổi 2020).
# LƯU Ý: văn bản này CHƯA có trong thư mục data/, nên đánh dấu external=True để minh bạch.
AGE_RULE_BASIS = "Luật Xử lý vi phạm hành chính 2012 (sửa đổi, bổ sung 2020), Điều 5, Điều 22 và Điều 134"


@dataclass
class RuleStep:
    rule: str
    basis: str
    detail: str
    external: bool = False


@dataclass
class QueryFacts:
    subjects: list[str]
    subject_detected: bool
    age: int | None
    article_refs: list[int | str]
    doc_hints: list[str]
    age_band: str | None = None
    invalid_docs: list[str] = field(default_factory=list)
    out_of_scope_docs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Hiểu câu hỏi bằng luật (rule-based NLU) - không tốn lời gọi LLM, kết quả tái lập được
# ---------------------------------------------------------------------------
_ORG_PATTERN = re.compile(
    r"\b(công ty|doanh nghiệp|cơ quan|đơn vị|tập đoàn|pháp nhân|nhà mạng|nhà cung cấp|"
    r"ngân hàng|cửa hàng|chi nhánh|startup|website của công ty|fanpage của công ty)"
    r"(\s+(của\s+)?(tôi|mình|chúng tôi|em|anh|chị|bạn))?\b",
    re.IGNORECASE,
)
_ORG_ENTITY_PATTERN = re.compile(
    r"\btổ\s+chức(?=\s*(?:,|/|có\b|là\b|vi\s+phạm\b|thực\s+hiện\b|bị\s+xử\s+phạt\b|này\b|đó\b|nào\b))",
    re.IGNORECASE,
)
_IND_PATTERN = re.compile(
    r"\b(cá nhân|tôi|mình|em|anh|chị|người dùng|nhân viên|học sinh|sinh viên|công dân|"
    r"người chơi|một người|người nào|ai đó|bạn)\b",
    re.IGNORECASE,
)
# Loại bỏ cụm xưng hô xã giao khi đặt câu hỏi ("cho tôi hỏi", "em xin hỏi"...) trước khi nhận diện chủ thể
_POLITE_PREFIX_PATTERN = re.compile(
    r"\b(?:cho\s+|xin\s+)?(?:tôi|mình|em|anh|chị|bạn|chúng\s+tôi)\s+"
    r"(?:xin\s+)?(?:hỏi|nhờ|tư\s+vấn|tra\s+cứu)\b",
    re.IGNORECASE,
)
# Nhận diện chính xác các cụm khoảng tuổi pháp lý trước khi bắt số tuổi đơn lẻ
_AGE_SPAN_14_16 = re.compile(
    r"(?:từ\s+)?(?:đủ\s+)?14\s*(?:tuổi\s*)?(?:đến|tới|-|–)\s*(?:dưới\s+)?16\s*tuổi",
    re.IGNORECASE,
)
_AGE_SPAN_16_18 = re.compile(
    r"(?:từ\s+)?(?:đủ\s+)?16\s*(?:tuổi\s*)?(?:đến|tới|-|–)\s*(?:dưới\s+)?18\s*tuổi",
    re.IGNORECASE,
)
_AGE_UNDER_14 = re.compile(r"dưới\s+14\s*tuổi", re.IGNORECASE)
_AGE_UNDER_16 = re.compile(r"dưới\s+16\s*tuổi", re.IGNORECASE)
_AGE_UNDER_18 = re.compile(r"dưới\s+18\s*tuổi", re.IGNORECASE)
_EXACT_AGE_PATTERN = re.compile(r"(?<!dưới\s)(?<!dưới\s\s)\b(\d{1,2})\s*tuổi", re.IGNORECASE)
_MINOR_PATTERN = re.compile(r"\b(trẻ em|vị thành niên|chưa thành niên)\b", re.IGNORECASE)
_ARTICLE_PATTERN = re.compile(r"Điều\s+(\d{1,3})\s*([a-z]?)(?![\w])", re.IGNORECASE)
_DOC_CODE_PATTERN = re.compile(r"(\d+/\d{4}/(?:NĐ-CP|ND-CP|QH\d{1,2}|VBHN-[A-ZĐ0-9\-]+))", re.IGNORECASE)
_DECREE_PATTERN = re.compile(r"(?:ngh[iị]\s*[dđ][iị]nh|\bn[dđ]\b)(?:\s+s[oố])?\s*(\d+)", re.IGNORECASE)


def _extract_age(text: str) -> tuple[int | None, str | None]:
    if _AGE_SPAN_14_16.search(text):
        return 15, "14_TO_UNDER_16"
    if _AGE_SPAN_16_18.search(text):
        return 17, "16_TO_UNDER_18"
    if _AGE_UNDER_14.search(text):
        return 13, "UNDER_14"
    if _AGE_UNDER_16.search(text):
        # This range crosses the legal boundary at age 14; do not pretend it means age 15.
        return None, "UNDER_16_UNSPECIFIED"
    if _AGE_UNDER_18.search(text):
        return None, "UNDER_18_UNSPECIFIED"
    exact = _EXACT_AGE_PATTERN.search(text)
    if exact:
        preceding = text[max(0, exact.start() - 30):exact.start()].lower()
        if re.search(r"(?:website|web\s*site|trang\s*web|công\s*ty|doanh\s*nghiệp|ứng\s*dụng|app)(?:\s+\S+){0,3}\s*$", preceding):
            return None, None
        age = int(exact.group(1))
        return (age, "UNDER_14" if age < 14 else "14_TO_UNDER_16" if age < 16 else "16_TO_UNDER_18" if age < 18 else "ADULT")
    return None, None


def analyze_question(question: str) -> QueryFacts:
    text = unicodedata.normalize("NFC", question or "")
    cleaned_for_subject = _POLITE_PREFIX_PATTERN.sub(" ", text)

    subjects: list[str] = []
    if _ORG_PATTERN.search(cleaned_for_subject) or _ORG_ENTITY_PATTERN.search(cleaned_for_subject):
        subjects.append(ORGANIZATION)
    # Bỏ cụm "công ty tôi" và đại từ xã giao trước khi tìm chủ thể cá nhân để tránh nhận nhầm
    residual = _ORG_PATTERN.sub(" ", _ORG_ENTITY_PATTERN.sub(" ", cleaned_for_subject))
    age, age_band = _extract_age(text)
    if _IND_PATTERN.search(residual) or age is not None or age_band is not None or _MINOR_PATTERN.search(text):
        subjects.append(INDIVIDUAL)
    detected = bool(subjects)
    if not subjects:
        subjects = [ORGANIZATION, INDIVIDUAL]

    if age is not None and INDIVIDUAL not in subjects:
        subjects.append(INDIVIDUAL)

    doc_hints: list[str] = []
    invalid_docs: list[str] = []
    out_of_scope_docs: list[str] = []
    invalid_numbers: set[int] = set()

    # Nhận diện theo tên Luật bằng tiếng Việt (VD: "Luật An ninh mạng", "Luật CNTT"...)
    for pattern, mapped_code in LAW_NAME_HINTS:
        if pattern.search(text) and mapped_code not in doc_hints:
            doc_hints.append(mapped_code)

    # Nhận diện mã văn bản đầy đủ (ví dụ: 15/2020/NĐ-CP, 24/2018/QH14, 9999/2025/NĐ-CP)
    for code in _DOC_CODE_PATTERN.findall(text):
        normalized_code = code.upper().replace("ND-CP", "NĐ-CP")
        if normalized_code in VALID_DOC_CODES:
            if normalized_code not in doc_hints:
                doc_hints.append(normalized_code)
        elif normalized_code in OUT_OF_SCOPE_DOC_CODES:
            out_name = OUT_OF_SCOPE_DOC_CODES[normalized_code]
            if out_name not in out_of_scope_docs:
                out_of_scope_docs.append(out_name)
        else:
            prefix_label = "Nghị định " if "NĐ-CP" in normalized_code else "Văn bản "
            full_unknown = f"{prefix_label}{normalized_code}"
            if full_unknown not in invalid_docs:
                invalid_docs.append(full_unknown)

    # Nhận diện số hiệu Nghị định viết tắt (ví dụ: Nghị định 15, Nghị định 13, Nghị định 147, Nghị định 10000...)
    for dec_num_str in _DECREE_PATTERN.findall(text):
        num = int(dec_num_str)
        if num in KNOWN_DECREE_NUMBERS:
            mapped_dec = KNOWN_DECREE_NUMBERS[num]
            if mapped_dec not in doc_hints:
                doc_hints.append(mapped_dec)
        elif num == 2020:
            if "15/2020/NĐ-CP" not in doc_hints:
                doc_hints.append("15/2020/NĐ-CP")
        elif 1990 <= num <= 2035:
            # Người dùng nhắc đến năm ban hành (VD: "Nghị định 2023", "Nghị định 2024"), không phải nghị định giả
            continue
        elif num in OUT_OF_SCOPE_DECREE_NUMBERS:
            if not any(str(num) in d for d in out_of_scope_docs):
                out_of_scope_docs.append(f"Nghị định {num}")
        else:
            # A bare number does not identify a legal instrument or its year.
            # Treat it as unavailable in the corpus rather than asserting scope/existence.
            if num not in invalid_numbers:
                invalid_numbers.add(num)
                invalid_docs.append(f"Nghị định số {num} (chưa rõ năm; không có trong kho dữ liệu)")

    return QueryFacts(
        subjects=subjects,
        subject_detected=detected,
        age=age,
        age_band=age_band,
        article_refs=sorted(
            {
                f"{num_part}{suffix.lower()}" if suffix else int(num_part)
                for num_part, suffix in _ARTICLE_PATTERN.findall(text)
            },
            key=lambda number: (int(re.match(r"\d+", str(number)).group()), str(number).lower()),
        ),
        doc_hints=doc_hints,
        invalid_docs=invalid_docs,
        out_of_scope_docs=out_of_scope_docs,
    )


def requires_out_of_scope_guardrail(facts: QueryFacts) -> bool:
    """Block known out-of-scope instruments unless the question also names a corpus document."""
    return bool(facts.out_of_scope_docs and not facts.doc_hints)


# ---------------------------------------------------------------------------
# Suy luận mức phạt
# ---------------------------------------------------------------------------
def format_vnd(amount: int | float | None) -> str:
    if amount is None:
        return "?"
    return f"{int(round(amount)):,}".replace(",", ".") + " đồng"


def _individual_cap(config: dict, article_number: int | str):
    try:
        art_num = int(re.match(r"\d+", str(article_number)).group())
    except (ValueError, AttributeError):
        return None, None
    for (low, high), cap, field_name in config.get("individual_caps", []):
        if low <= art_num <= high:
            return cap, field_name
    return None, None


_AGE_BANDS_NEEDING_EXACT_AGE = {"UNDER_16_UNSPECIFIED", "UNDER_18_UNSPECIFIED"}

_AGE_RANGE_NEEDS_EXACT_AGE_DETAIL = (
    "Khoảng tuổi được nêu đi qua mốc 14 hoặc 16 tuổi; cần tuổi chính xác trước khi áp dụng quy tắc cho người chưa thành niên. "
    "Theo Điều 5, Điều 22 và Điều 134 Luật Xử lý vi phạm hành chính: "
    "Người dưới 14 tuổi không bị xử phạt vi phạm hành chính; "
    "người từ đủ 14 tuổi đến dưới 16 tuổi chỉ bị áp dụng hình thức xử phạt cảnh cáo (không phạt tiền); "
    "người từ đủ 16 tuổi đến dưới 18 tuổi mức phạt tiền không quá 1/2 mức phạt áp dụng đối với người thành niên."
)


def _leading_article_int(article_number: int | str) -> int | None:
    """Phần số nguyên đứng đầu của số Điều ("93a" -> 93, "114a" -> 114, "abc" -> None)."""
    match_num = re.match(r"^(\d+)", str(article_number).strip())
    return int(match_num.group(1)) if match_num else None


def _unsupported_penalty_result() -> dict:
    return {"results": [], "steps": [], "rule_supported": False}


def _resolve_base_subject(
    config: dict, article_number: int | str, art_int: int, base_min, base_max
) -> tuple[str, RuleStep]:
    """Chủ thể gốc của khung phạt: theo Điều 4 khoản 3 mặc định là TỔ CHỨC, trừ các Điều ngoại lệ."""
    exceptions = config["individual_base_articles"]
    if article_number in exceptions or art_int in exceptions:
        return INDIVIDUAL, RuleStep(
            "BASE_SUBJECT", config["basis"],
            f"Điều {article_number} là ngoại lệ của Điều 4 khoản 3: khung "
            f"{format_vnd(base_min)} - {format_vnd(base_max)} áp dụng trực tiếp cho cá nhân.",
        )
    return config["base_subject"], RuleStep(
        "BASE_SUBJECT", config["basis"],
        f"Khung {format_vnd(base_min)} - {format_vnd(base_max)} tại Điều {article_number} "
        "là mức phạt áp dụng đối với TỔ CHỨC.",
    )


def _evaluate_individual(
    config: dict,
    article_number: int | str,
    base_subject: str,
    base_min,
    base_max,
    facts: QueryFacts,
    steps: list[RuleStep],
) -> tuple[bool, float | None, float, str]:
    """Quy tắc cho CÁ NHÂN: độ tuổi (Luật XLVPHC) -> quy đổi 1/2 -> trần lĩnh vực -> trần 16-18 tuổi.

    Trả về (applicable, amount_min, amount_max, formula); dấu vết suy luận được ghi vào `steps`.
    """
    age = facts.age

    # Các trường hợp không phạt tiền: khoảng tuổi mơ hồ, dưới 14 tuổi, từ đủ 14 đến dưới 16 tuổi.
    if facts.age_band in _AGE_BANDS_NEEDING_EXACT_AGE:
        steps.append(RuleStep("AGE_RANGE_NEEDS_EXACT_AGE", AGE_RULE_BASIS, _AGE_RANGE_NEEDS_EXACT_AGE_DETAIL, True))
        return False, base_min, base_max, "Cần biết tuổi chính xác để xác định hình thức và mức xử lý"
    if age is not None and age < 14:
        steps.append(RuleStep("AGE_UNDER_14", AGE_RULE_BASIS,
                              f"Người {age} tuổi chưa đủ tuổi chịu xử phạt VPHC.", True))
        return False, base_min, base_max, "Dưới 14 tuổi: không bị xử phạt vi phạm hành chính"
    if age is not None and age < 16:
        steps.append(RuleStep("AGE_14_16", AGE_RULE_BASIS,
                              f"Người {age} tuổi chỉ bị xử phạt khi vi phạm do cố ý và "
                              "áp dụng hình thức cảnh cáo, không phạt tiền.", True))
        return False, base_min, base_max, "Từ đủ 14 đến dưới 16 tuổi: phạt cảnh cáo, không phạt tiền"

    amount_min, amount_max, formula = base_min, base_max, "giữ nguyên khung gốc"

    if base_subject == ORGANIZATION:
        ratio = config["individual_ratio"]
        amount_min, amount_max = base_min * ratio, base_max * ratio
        formula = "Cá nhân = 1/2 × mức phạt Tổ chức"
        steps.append(RuleStep(
            "INDIVIDUAL_HALF", config["basis"],
            f"Cá nhân vi phạm như tổ chức -> {format_vnd(base_min)} × 1/2 = "
            f"{format_vnd(amount_min)}; {format_vnd(base_max)} × 1/2 = {format_vnd(amount_max)}.",
        ))

    cap, field_name = _individual_cap(config, article_number)
    if cap is not None:
        ok = amount_max <= cap
        steps.append(RuleStep(
            "CAP_CHECK", config["cap_basis"],
            f"Kiểm tra trần lĩnh vực {field_name}: {format_vnd(amount_max)} "
            f"{'≤' if ok else '>'} {format_vnd(cap)} -> {'hợp lệ' if ok else 'VƯỢT TRẦN, giới hạn lại'}.",
        ))
        if not ok:
            amount_max = cap
            amount_min = min(amount_min, cap)

    # Từ đủ 16 đến dưới 18 tuổi: chỉ xác định được mức trần (1/2 mức tối đa của người thành niên).
    if age is not None and age < 18:
        amount_min, amount_max = None, amount_max / 2
        formula = "Người từ đủ 16 đến dưới 18 tuổi: mức phạt không quá 1/2 mức tối đa của người thành niên"
        steps.append(RuleStep("AGE_16_18", AGE_RULE_BASIS,
                              f"Người {age} tuổi: mức phạt tiền không quá 1/2 mức tối đa của người thành niên, tức không quá {format_vnd(amount_max)}. Mức cụ thể chưa được xác định.", True))

    return True, amount_min, amount_max, formula


def _penalty_display(applicable: bool, amount_min, amount_max, formula: str) -> str:
    if not applicable:
        return formula
    if amount_min is None:
        return f"Không quá {format_vnd(amount_max)}; mức cụ thể chưa được xác định"
    return f"{format_vnd(amount_min)} - {format_vnd(amount_max)}"


def apply_penalty_rules(
    penalty: dict, doc_code: str, article_number: int | str, facts: QueryFacts
) -> dict:
    """Tính mức phạt áp dụng cho từng chủ thể trong câu hỏi + dấu vết suy luận."""
    base_min, base_max = penalty.get("min_amount"), penalty.get("max_amount")
    art_int = _leading_article_int(article_number)

    if penalty.get("type") != "FINE" or base_min is None or base_max is None or art_int is None:
        return _unsupported_penalty_result()

    config = DECREE_RULES.get(doc_code)
    if config is None or not (config["scope"][0] <= art_int <= config["scope"][1]):
        # Do not apply Nghị định 15/2020's subject/age rules to unrelated instruments.
        return _unsupported_penalty_result()

    base_subject, base_step = _resolve_base_subject(config, article_number, art_int, base_min, base_max)
    steps: list[RuleStep] = [base_step]
    results: list[dict] = []

    for subject in facts.subjects:
        applicable, amount_min, amount_max, formula = True, base_min, base_max, "giữ nguyên khung gốc"

        if subject == INDIVIDUAL:
            applicable, amount_min, amount_max, formula = _evaluate_individual(
                config, article_number, base_subject, base_min, base_max, facts, steps
            )
        elif subject == ORGANIZATION and base_subject == INDIVIDUAL:
            applicable, formula = False, "Không áp dụng cho tổ chức"
            steps.append(RuleStep(
                "NOT_APPLICABLE", config["basis"],
                f"Điều {article_number} chỉ điều chỉnh hành vi của cá nhân (người chơi).",
            ))

        results.append({
            "subject": subject,
            "subject_label": SUBJECT_LABELS.get(subject, subject),
            "applicable": applicable,
            "min_amount": int(round(amount_min)) if applicable and amount_min is not None else None,
            "max_amount": int(round(amount_max)) if applicable else None,
            "display": _penalty_display(applicable, amount_min, amount_max, formula),
            "formula": formula,
        })

    return {"base_subject": base_subject, "results": results, "steps": [asdict(s) for s in steps], "rule_supported": True}


# ---------------------------------------------------------------------------
# Chuẩn hóa Quy phạm (Norm / Rule Classification) & Nguồn gốc kiểm chứng (Provenance)
# ---------------------------------------------------------------------------
class NormType:
    OBLIGATION = "OBLIGATION"    # Nghĩa vụ / Trách nhiệm (phải thực hiện)
    RIGHT = "RIGHT"              # Quyền / Cho phép (được phép, có quyền)
    PROHIBITION = "PROHIBITION"  # Cấm đoán / Vi phạm (không được, nghiêm cấm)
    CONDITION = "CONDITION"      # Điều kiện áp dụng
    EXCEPTION = "EXCEPTION"      # Ngoại lệ (trừ trường hợp)


class VerificationStatus:
    VERIFIED = "VERIFIED"        # Đã đối soát chuẩn văn bản gốc
    CANDIDATE = "CANDIDATE"      # Ứng viên sinh từ LLM, cần kiểm chứng


@dataclass
class ProvenanceRef:
    source_code: str             # Mã văn bản (VD: 15/2020/NĐ-CP)
    article_number: int | str    # Điều số
    clause_number: int | None = None
    point_letter: str | None = None
    page: int | None = None
    quote: str = ""              # Trích đoạn chứng minh gốc
    source_url: str | None = None
    extractor_version: str = "v2.2-hybrid"
    status: str = VerificationStatus.VERIFIED


# ---------------------------------------------------------------------------
# Suy luận Đa chặng 3 Tầng (Multi-Hop Legal Graph: Quy phạm -> Hành chính -> Hình sự)
# ---------------------------------------------------------------------------
_BLHS_CODE = "100/2015/QH13"
_BLHS_SOURCE = "Bộ luật Hình sự số 100/2015/QH13 (sửa đổi, bổ sung 2017)"
# Số Điều rỗng/không xác định khi hỏi chung về BLHS -> cho phép khớp theo từ khóa hành vi.
_UNSPECIFIED_ARTICLE_TOKENS = {"", "0", "none"}

# Các nhóm văn bản luật nền dùng chung giữa nhiều tội danh.
_CYBERATTACK_LAW_ARTICLES = {
    "24/2018/QH14": {"7", "8", "18", "19"},
    "116/2025/QH15": {"7", "8", "18", "19"},
    "86/2015/QH13": {"7", "8", "18", "19"},
}
_MALWARE_LAW_ARTICLES = {
    "86/2015/QH13": {"7", "8"},
    "24/2018/QH14": {"7", "8"},
    "116/2025/QH15": {"7", "8"},
}


@dataclass(frozen=True)
class _CriminalEscalationRule:
    """Một tội danh BLHS + các Điều (hành chính / luật chuyên ngành) có thể dẫn chiếu tới nó."""
    article: int
    source_articles: dict[str, set[str]]  # doc_code -> các số Điều (dạng chuỗi chữ thường)
    keywords: tuple[str, ...]
    title: str
    condition: str
    penalty: str

    def is_candidate(self, doc_code: str, art_str: str) -> bool:
        if doc_code == _BLHS_CODE:
            return art_str == str(self.article) or art_str in _UNSPECIFIED_ARTICLE_TOKENS
        return art_str in self.source_articles.get(doc_code, ())

    def matches(self, doc_code: str, art_str: str, norm_act: str) -> bool:
        if doc_code == _BLHS_CODE and art_str == str(self.article):
            return True
        return any(kw in norm_act for kw in self.keywords)

    def to_dict(self) -> dict:
        return {
            "code": _BLHS_CODE,
            "article": self.article,
            "title": self.title,
            "condition": self.condition,
            "penalty": self.penalty,
            "source": _BLHS_SOURCE,
            "status": VerificationStatus.VERIFIED,
        }


# Thứ tự ưu tiên đánh giá (trả về tội danh khớp đầu tiên) - giữ nguyên như quy tắc gốc.
CRIMINAL_ESCALATION_RULES: tuple[_CriminalEscalationRule, ...] = (
    # Nhóm 1: Tán phát thông tin sai sự thật / vu khống / xúc phạm / thông tin giả / chủ quyền
    # (Điều 99, 101 NĐ 15/2020; Điều 93, 95 NĐ 174/2026; Điều 7, 8, 18 Luật ANM; Điều 7 Luật AI; Điều 288 BLHS)
    _CriminalEscalationRule(
        article=288,
        source_articles={
            "15/2020/NĐ-CP": {"99", "101"},
            "174/2026/NĐ-CP": {"93", "95"},
            "24/2018/QH14": {"7", "8", "18"},
            "116/2025/QH15": {"7", "8", "18"},
            "134/2025/QH15": {"7"},
        },
        keywords=("sai sự thật", "bịa đặt", "vu khống", "xúc phạm", "thông tin giả", "xuyên tạc", "chủ quyền", "bản đồ", "đưa thông tin trái phép", "deepfake", "giả mạo"),
        title="Điều 288 BLHS 2015 (sửa đổi 2017): Tội đưa hoặc sử dụng trái phép thông tin mạng máy tính, mạng viễn thông",
        condition="Thu lợi bất chính từ 50.000.000 đồng trở lên, gây thiệt hại từ 100.000.000 đồng trở lên hoặc gây dư luận xấu làm giảm uy tín của cơ quan, tổ chức, cá nhân",
        penalty="Phạt tiền từ 30.000.000 đến 1.000.000.000 đồng hoặc phạt tù từ 06 tháng đến 07 năm",
    ),
    # Nhóm 2: Xâm nhập, bẻ khóa, chiếm quyền điều khiển hệ thống mạng
    # (Điều 80, 81 NĐ 15/2020; Điều 89, 90 NĐ 174/2026; Điều 7, 8, 18, 19 Luật ANM / Luật ATTTM; Điều 289 BLHS)
    _CriminalEscalationRule(
        article=289,
        source_articles={"15/2020/NĐ-CP": {"80", "81"}, "174/2026/NĐ-CP": {"89", "90"}, **_CYBERATTACK_LAW_ARTICLES},
        keywords=("bẻ khóa", "truy cập trái phép", "xâm nhập", "chiếm quyền", "vượt qua mã truy cập", "can thiệp dữ liệu"),
        title="Điều 289 BLHS 2015 (sửa đổi 2017): Tội xâm nhập trái phép vào mạng máy tính, mạng viễn thông hoặc phương tiện điện tử của người khác",
        condition="Cố ý vượt qua cảnh báo, mã truy cập, tường lửa để chiếm quyền điều khiển hoặc can thiệp dữ liệu",
        penalty="Phạt tiền từ 50.000.000 đến 300.000.000 đồng hoặc phạt tù từ 01 năm đến 12 năm",
    ),
    # Nhóm 3: Sản xuất, mua bán, trao đổi công cụ, phần mềm độc hại
    # (Điều 77 NĐ 15/2020; Điều 86 NĐ 174/2026; Điều 7, 8 Luật ATTTM / Luật ANM 2018; Điều 285 BLHS)
    _CriminalEscalationRule(
        article=285,
        source_articles={"15/2020/NĐ-CP": {"77"}, "174/2026/NĐ-CP": {"86"}, **_MALWARE_LAW_ARTICLES},
        keywords=("sản xuất công cụ", "mua bán công cụ", "phần mềm độc hại", "thiết bị bẻ khóa", "công cụ tấn công", "chế tạo mã độc", "phần mềm tấn công", "sản xuất, phát tán hoặc mua bán", "công cụ, thiết bị, phần mềm"),
        title="Điều 285 BLHS 2015 (sửa đổi 2017): Tội sản xuất, mua bán, trao đổi hoặc tặng cho công cụ, thiết bị, phần mềm để sử dụng vào mục đích trái pháp luật",
        condition="Thu lợi bất chính từ 30.000.000 đồng trở lên hoặc gây thiệt hại từ 50.000.000 đồng trở lên",
        penalty="Phạt tiền từ 20.000.000 đến 500.000.000 đồng hoặc phạt tù từ 01 năm đến 07 năm",
    ),
    # Nhóm 4: Phát tán chương trình tin học gây hại (virus, trojan, ransomware)
    # (Điều 78 NĐ 15/2020; Điều 87 NĐ 174/2026; Điều 7, 8 Luật ATTTM / Luật ANM 2018; Điều 286 BLHS)
    _CriminalEscalationRule(
        article=286,
        source_articles={"15/2020/NĐ-CP": {"78"}, "174/2026/NĐ-CP": {"87"}, **_MALWARE_LAW_ARTICLES},
        keywords=("phát tán virus", "phát tán mã độc", "lây lan mã độc", "ransomware", "mã hóa tống tiền", "chương trình gây hại", "mã độc", "tê liệt hệ thống", "chương trình tin học"),
        title="Điều 286 BLHS 2015 (sửa đổi 2017): Tội phát tán chương trình tin học gây hại cho hoạt động của mạng máy tính, mạng viễn thông, phương tiện điện tử",
        condition="Thu lợi bất chính từ 50.000.000 đồng trở lên hoặc làm đình trệ hoạt động mạng từ 30 phút trở lên hoặc gây thiệt hại từ 100.000.000 đồng trở lên",
        penalty="Phạt tiền từ 50.000.000 đến 1.000.000.000 đồng hoặc phạt tù từ 01 năm đến 12 năm",
    ),
    # Nhóm 5: Cản trở, gây rối loạn hoạt động mạng, tấn công từ chối dịch vụ (DDoS)
    # (Điều 79 NĐ 15/2020; Điều 88 NĐ 174/2026; Điều 7, 8, 18, 19 Luật ANM / Luật ATTTM; Điều 287 BLHS)
    _CriminalEscalationRule(
        article=287,
        source_articles={"15/2020/NĐ-CP": {"79"}, "174/2026/NĐ-CP": {"88"}, **_CYBERATTACK_LAW_ARTICLES},
        keywords=("ddos", "từ chối dịch vụ", "gây nghẽn mạng", "làm tê liệt", "phá hoại mạng", "rối loạn hoạt động", "cản trở", "rối loạn", "tê liệt"),
        title="Điều 287 BLHS 2015 (sửa đổi 2017): Tội cản trở hoặc gây rối loạn hoạt động của mạng máy tính, mạng viễn thông, phương tiện điện tử",
        condition="Thu lợi bất chính từ 50.000.000 đồng trở lên hoặc gây thiệt hại từ 100.000.000 đồng trở lên hoặc làm tê liệt hệ thống thông tin",
        penalty="Phạt tiền từ 30.000.000 đến 1.000.000.000 đồng hoặc phạt tù từ 06 tháng đến 12 năm",
    ),
    # Nhóm 6: Lừa đảo, chiếm đoạt tài sản qua mạng viễn thông / mạng máy tính
    # (Điều 82 NĐ 15/2020; Điều 91 NĐ 174/2026; Điều 7, 8, 18, 19 Luật ANM / Luật ATTTM; Điều 290 BLHS)
    _CriminalEscalationRule(
        article=290,
        source_articles={"15/2020/NĐ-CP": {"82"}, "174/2026/NĐ-CP": {"91"}, **_CYBERATTACK_LAW_ARTICLES},
        keywords=("lừa đảo qua mạng", "chiếm đoạt tài sản", "trộm cắp tài khoản", "hack tài khoản", "lừa đảo viễn thông", "chiếm đoạt", "giả mạo ngân hàng", "tài khoản", "lừa đảo"),
        title="Điều 290 BLHS 2015 (sửa đổi 2017): Tội sử dụng mạng máy tính, mạng viễn thông, phương tiện điện tử thực hiện hành vi chiếm đoạt tài sản",
        condition="Chiếm đoạt tài sản trị giá từ 2.000.000 đồng trở lên (hoặc dưới 2.000.000 đồng nhưng đã bị xử phạt VPHC hoặc kết án chưa xóa án tích)",
        penalty="Phạt cải tạo không giam giữ đến 03 năm hoặc phạt tù từ 06 tháng đến 20 năm",
    ),
)


def infer_criminal_escalation(doc_code: str, article_number: int | str, action_name: str = "") -> list[dict]:
    """Suy luận chuyển hóa hình sự có kiểm chứng nguồn và ngưỡng cấu thành (Multi-Hop 3-Tier Legal Graph)."""
    norm_doc = unicodedata.normalize("NFC", str(doc_code or "")).strip().upper().replace("ND-CP", "NĐ-CP")
    norm_act = unicodedata.normalize("NFC", str(action_name or "")).lower().strip()
    art_str = unicodedata.normalize("NFC", str(article_number if article_number is not None else "")).lower().strip()
    art_str = re.sub(r"^điều\s+", "", art_str).strip()

    for rule in CRIMINAL_ESCALATION_RULES:
        if rule.is_candidate(norm_doc, art_str) and rule.matches(norm_doc, art_str, norm_act):
            return [rule.to_dict()]
    return []

