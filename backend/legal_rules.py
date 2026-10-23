"""Bộ suy luận luật tất định (Deterministic Legal Rule Engine) - linh hồn của khối Symbolic.

Nguyên tắc: LLM KHÔNG được tự tính toán số tiền. Mọi phép tính mức phạt theo chủ thể,
độ tuổi, mức trần... được thực hiện bằng Python thuần và trả về kèm "dấu vết suy luận"
(rule trace) có căn cứ pháp lý để hiển thị lên giao diện.
"""

from __future__ import annotations

import re
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
        "scope": (5, 113),  # Chương II (Điều 5) -> Chương VII (Điều 113)
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
        ],
        "cap_basis": "Điều 4 khoản 1, 2 Nghị định 15/2020/NĐ-CP",
    }
}

VALID_DOC_CODES = {
    "15/2020/NĐ-CP",
    "14/2022/NĐ-CP",
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

KNOWN_DECREE_NUMBERS: dict[int, str] = {
    15: "15/2020/NĐ-CP",
    14: "15/2020/NĐ-CP",
    26: "26/2026/VBHN-BKHCN",
    13: "13/2023/NĐ-CP",
    23: "23/2025/NĐ-CP",
    52: "52/2013/NĐ-CP",
    85: "85/2016/NĐ-CP",
    142: "142/2026/NĐ-CP",
    147: "147/2024/NĐ-CP",
    163: "163/2024/NĐ-CP",
    165: "165/2025/NĐ-CP",
    224: "224/2026/NĐ-CP",
    248: "248/2026/NĐ-CP",
    333: "333/2026/NĐ-CP",
    356: "356/2025/NĐ-CP",
}

LAW_NAME_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"luật\s+an\s+ninh\s+mạng\s*2025", re.IGNORECASE), "116/2025/QH15"),
    (re.compile(r"luật\s+an\s+ninh\s+mạng(?!\s*2025)", re.IGNORECASE), "24/2018/QH14"),
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
    (re.compile(r"bộ\s+luật\s+hình\s+sự", re.IGNORECASE), "100/2015/QH13"),
    (re.compile(r"bộ\s+luật\s+dân\s+sự", re.IGNORECASE), "91/2015/QH13"),
]

# Quy tắc độ tuổi - Luật Xử lý vi phạm hành chính 2012 (sửa đổi 2020).
# LƯU Ý: văn bản này CHƯA có trong thư mục data/, nên đánh dấu external=True để minh bạch.
AGE_RULE_BASIS = "Luật Xử lý vi phạm hành chính 2012 (sửa đổi, bổ sung 2020), Điều 5 và Điều 134"


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
    article_refs: list[int]
    doc_hints: list[str]
    invalid_docs: list[str] = field(default_factory=list)
    out_of_scope_docs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Hiểu câu hỏi bằng luật (rule-based NLU) - không tốn lời gọi LLM, kết quả tái lập được
# ---------------------------------------------------------------------------
_ORG_PATTERN = re.compile(
    r"\b(công ty|doanh nghiệp|tổ chức|cơ quan|đơn vị|tập đoàn|pháp nhân|nhà mạng|nhà cung cấp|"
    r"ngân hàng|cửa hàng|chi nhánh|startup|website của công ty|fanpage của công ty)"
    r"(\s+(của\s+)?(tôi|mình|chúng tôi|em|anh|chị|bạn))?\b",
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
_ARTICLE_PATTERN = re.compile(r"Điều\s+(\d{1,3})", re.IGNORECASE)
_DOC_CODE_PATTERN = re.compile(r"(\d+/\d{4}/(?:NĐ-CP|ND-CP|QH\d{1,2}|VBHN-[A-ZĐ0-9\-]+))", re.IGNORECASE)
_DECREE_PATTERN = re.compile(r"(?:ngh[iị]\s*[dđ][iị]nh)(?:\s+s[oố])?\s*(\d+)", re.IGNORECASE)


def _extract_age(text: str) -> int | None:
    if _AGE_SPAN_14_16.search(text):
        return 15
    if _AGE_SPAN_16_18.search(text):
        return 17
    if _AGE_UNDER_14.search(text):
        return 13
    exact = _EXACT_AGE_PATTERN.search(text)
    if exact:
        return int(exact.group(1))
    if _AGE_UNDER_16.search(text):
        return 15
    if _AGE_UNDER_18.search(text):
        return 17
    return None


def analyze_question(question: str) -> QueryFacts:
    text = question or ""
    cleaned_for_subject = _POLITE_PREFIX_PATTERN.sub(" ", text)

    subjects: list[str] = []
    if _ORG_PATTERN.search(cleaned_for_subject):
        subjects.append(ORGANIZATION)
    # Bỏ cụm "công ty tôi" và đại từ xã giao trước khi tìm chủ thể cá nhân để tránh nhận nhầm
    residual = _ORG_PATTERN.sub(" ", cleaned_for_subject)
    age = _extract_age(text)
    if _IND_PATTERN.search(residual) or age is not None or _MINOR_PATTERN.search(text):
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
        num_prefix = int(normalized_code.split("/")[0])
        if num_prefix > 500:
            # Số thứ tự văn bản vượt ngưỡng thực tế -> Văn bản giả mạo / không tồn tại
            invalid_numbers.add(num_prefix)
            prefix_label = "Nghị định " if "NĐ-CP" in normalized_code else "Văn bản "
            full_invalid = f"{prefix_label}{normalized_code}"
            if full_invalid not in invalid_docs:
                invalid_docs.append(full_invalid)
        elif normalized_code in VALID_DOC_CODES:
            mapped = "15/2020/NĐ-CP" if normalized_code == "14/2022/NĐ-CP" else normalized_code
            if mapped not in doc_hints:
                doc_hints.append(mapped)
        else:
            out_of_scope_docs.append(normalized_code)

    # Nhận diện số hiệu Nghị định viết tắt (ví dụ: Nghị định 15, Nghị định 13, Nghị định 147, Nghị định 10000...)
    for dec_num_str in _DECREE_PATTERN.findall(text):
        num = int(dec_num_str)
        if num in KNOWN_DECREE_NUMBERS:
            mapped_dec = KNOWN_DECREE_NUMBERS[num]
            if mapped_dec not in doc_hints:
                doc_hints.append(mapped_dec)
        elif num > 500:
            if num not in invalid_numbers:
                invalid_numbers.add(num)
                invalid_docs.append(f"Nghị định {num}")
        else:
            label = f"Nghị định {num}"
            if label not in out_of_scope_docs and not any(str(num) in d for d in out_of_scope_docs):
                out_of_scope_docs.append(label)

    return QueryFacts(
        subjects=subjects,
        subject_detected=detected,
        age=age,
        article_refs=sorted({int(n) for n in _ARTICLE_PATTERN.findall(text)}),
        doc_hints=doc_hints,
        invalid_docs=invalid_docs,
        out_of_scope_docs=out_of_scope_docs,
    )


# ---------------------------------------------------------------------------
# Suy luận mức phạt
# ---------------------------------------------------------------------------
def format_vnd(amount: int | float | None) -> str:
    if amount is None:
        return "?"
    return f"{int(round(amount)):,}".replace(",", ".") + " đồng"


def _individual_cap(config: dict, article_number: int):
    for (low, high), cap, field_name in config.get("individual_caps", []):
        if low <= article_number <= high:
            return cap, field_name
    return None, None


def apply_penalty_rules(
    penalty: dict, doc_code: str, article_number: int, facts: QueryFacts
) -> dict:
    """Tính mức phạt áp dụng cho từng chủ thể trong câu hỏi + dấu vết suy luận."""
    base_min, base_max = penalty.get("min_amount"), penalty.get("max_amount")
    steps: list[RuleStep] = []
    results: list[dict] = []

    if penalty.get("type") != "FINE" or base_min is None or base_max is None:
        return {"results": results, "steps": [asdict(s) for s in steps]}

    config = DECREE_RULES.get(doc_code)
    low, high = config["scope"] if config else (0, -1)
    in_scope = config is not None and low <= article_number <= high

    if in_scope and article_number in config["individual_base_articles"]:
        base_subject = INDIVIDUAL
        steps.append(RuleStep(
            "BASE_SUBJECT", config["basis"],
            f"Điều {article_number} là ngoại lệ của Điều 4 khoản 3: khung "
            f"{format_vnd(base_min)} - {format_vnd(base_max)} áp dụng trực tiếp cho cá nhân.",
        ))
    elif in_scope:
        base_subject = config["base_subject"]
        steps.append(RuleStep(
            "BASE_SUBJECT", config["basis"],
            f"Khung {format_vnd(base_min)} - {format_vnd(base_max)} tại Điều {article_number} "
            "là mức phạt áp dụng đối với TỔ CHỨC.",
        ))
    else:
        base_subject = penalty.get("base_subject") or None
        steps.append(RuleStep(
            "BASE_SUBJECT", f"Văn bản {doc_code}",
            "Không có quy tắc quy đổi chủ thể cho văn bản này; giữ nguyên khung phạt gốc.",
        ))

    for subject in facts.subjects:
        amount_min, amount_max, formula = base_min, base_max, "giữ nguyên khung gốc"
        applicable = True

        if in_scope and base_subject == ORGANIZATION and subject == INDIVIDUAL:
            ratio = config["individual_ratio"]
            amount_min, amount_max = base_min * ratio, base_max * ratio
            formula = "Cá nhân = 1/2 × mức phạt Tổ chức"
            steps.append(RuleStep(
                "INDIVIDUAL_HALF", config["basis"],
                f"Cá nhân vi phạm như tổ chức -> {format_vnd(base_min)} × 1/2 = "
                f"{format_vnd(amount_min)}; {format_vnd(base_max)} × 1/2 = {format_vnd(amount_max)}.",
            ))
        elif in_scope and base_subject == INDIVIDUAL and subject == ORGANIZATION:
            applicable = False
            formula = "Không áp dụng cho tổ chức"
            steps.append(RuleStep(
                "NOT_APPLICABLE", config["basis"],
                f"Điều {article_number} chỉ điều chỉnh hành vi của cá nhân (người chơi).",
            ))

        if applicable and subject == INDIVIDUAL and in_scope:
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

        if applicable and subject == INDIVIDUAL and facts.age is not None:
            age = facts.age
            if age < 14:
                applicable = False
                formula = "Dưới 14 tuổi: không bị xử phạt vi phạm hành chính"
                steps.append(RuleStep("AGE_UNDER_14", AGE_RULE_BASIS,
                                      f"Người {age} tuổi chưa đủ tuổi chịu xử phạt VPHC.", True))
            elif age < 16:
                applicable = False
                formula = "Từ đủ 14 đến dưới 16 tuổi: phạt cảnh cáo, không phạt tiền"
                steps.append(RuleStep("AGE_14_16", AGE_RULE_BASIS,
                                      f"Người {age} tuổi chỉ bị xử phạt khi vi phạm do cố ý và "
                                      "áp dụng hình thức cảnh cáo, không phạt tiền.", True))
            elif age < 18:
                amount_min, amount_max = amount_min / 2, amount_max / 2
                formula += " -> người 16-18 tuổi: không quá 1/2 mức của người thành niên"
                steps.append(RuleStep("AGE_16_18", AGE_RULE_BASIS,
                                      f"Người {age} tuổi: mức phạt tiền tối đa = 1/2 -> "
                                      f"{format_vnd(amount_min)} - {format_vnd(amount_max)}.", True))

        results.append({
            "subject": subject,
            "subject_label": SUBJECT_LABELS.get(subject, subject),
            "applicable": applicable,
            "min_amount": int(round(amount_min)) if applicable else None,
            "max_amount": int(round(amount_max)) if applicable else None,
            "display": (f"{format_vnd(amount_min)} - {format_vnd(amount_max)}" if applicable else formula),
            "formula": formula,
        })

    return {"base_subject": base_subject, "results": results, "steps": [asdict(s) for s in steps]}
