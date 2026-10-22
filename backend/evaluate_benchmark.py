"""Đánh giá benchmark định lượng theo ba tiêu chí học thuật.

So sánh câu trả lời Naive Vector RAG và Neuro-Symbolic Hybrid RAG theo:
1. Độ chính xác trích dẫn điều luật/văn bản.
2. Độ chính xác mức phạt hoặc quy tắc độ tuổi.
3. Khả năng phân biệt chủ thể và tuân thủ guardrail.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
import unicodedata

from main import ChatRequest, chat_endpoint

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


BENCHMARK_CASES = [
    {
        "id": "TC01",
        "category": "Chủ thể Tổ chức vs Cá nhân",
        "question": (
            "Công ty tôi vô tình chia sẻ bài viết sai sự thật về dịch bệnh lên fanpage Facebook "
            "của công ty thì bị phạt bao nhiêu tiền? Nếu là nhân viên tự ý đăng thì mức phạt có khác không?"
        ),
        "citation_groups": [["điều 101"], ["15/2020"]],
        "required_amounts": [10_000_000, 20_000_000, 5_000_000],
        "subject_amounts": [
            {"subject": "organization", "amounts": [10_000_000, 20_000_000]},
            {"subject": "individual", "amounts": [5_000_000, 10_000_000]},
        ],
    },
    {
        "id": "TC02",
        "category": "Độ tuổi vị thành niên (14-16 tuổi)",
        "question": (
            "Một bạn học sinh 15 tuổi tạo đường link giả mạo trên mạng xã hội để tung tin sai sự thật "
            "thì bị xử lý phạt tiền như thế nào?"
        ),
        "citation_groups": [["điều 101"]],
        "fine_rule": "age_14_16",
        "subject_groups": [["15 tuổi", "từ đủ 14 đến dưới 16 tuổi", "14 đến dưới 16 tuổi"]],
    },
    {
        "id": "TC03",
        "category": "Mức phạt Cá nhân Điều 101",
        "question": (
            "Cá nhân có hành vi cung cấp, chia sẻ hình ảnh bản đồ Việt Nam nhưng không thể hiện đúng "
            "chủ quyền quốc gia trên mạng xã hội thì bị phạt bao nhiêu theo Điều 101 Nghị định 15/2020?"
        ),
        "citation_groups": [["điều 101"]],
        "required_amounts": [5_000_000, 10_000_000],
        "subject_amounts": [
            {"subject": "individual", "amounts": [5_000_000, 10_000_000]},
        ],
    },
    {
        "id": "TC04",
        "category": "Ngoại lệ chủ thể gốc là Cá nhân (Điều 106)",
        "question": (
            "Người chơi game online có hành vi lợi dụng trò chơi điện tử để thực hiện hành vi vi phạm "
            "pháp luật theo Điều 106 Nghị định 15/2020 thì bị phạt bao nhiêu?"
        ),
        "citation_groups": [["điều 106"]],
        "required_amounts": [2_000_000, 3_000_000],
        "subject_amounts": [
            {"subject": "player", "amounts": [2_000_000, 3_000_000]},
        ],
        "subject_groups": [
            ["người chơi", "cá nhân", "game thủ"],
            [
                "điều 106 là ngoại lệ",
                "ngoại lệ điều 106",
                "điều 106 áp dụng trực tiếp",
                "áp dụng trực tiếp cho người chơi",
                "mức phạt áp dụng trực tiếp cho cá nhân",
            ],
        ],
    },
    {
        "id": "TC05",
        "category": "Chống ảo giác văn bản giả mạo (Guardrail)",
        "question": (
            "Theo Nghị định 9999/2025/NĐ-CP thì hành vi bình luận xúc phạm người khác trên Facebook "
            "bị phạt bao nhiêu tiền?"
        ),
        "citation_groups": [["9999/2025/nd-cp", "nghi dinh 9999/2025"], ["không tồn tại", "không có thực"]],
        "fine_rule": "no_fabricated_fine",
        "subject_groups": [["không tồn tại", "không có thực"]],
    },
]


def _normalize(text: str) -> str:
    """Bỏ dấu tiếng Việt và chuẩn hóa chữ để so khớp không phụ thuộc dấu câu."""
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _contains_any(text: str, alternatives: list[str]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(option) in normalized for option in alternatives)


def _has_citations(answer: str, case: dict) -> bool:
    """Mỗi nhóm là một căn cứ bắt buộc; các cách viết trong nhóm là tương đương."""
    text = _normalize(answer)
    for group in case["citation_groups"]:
        found = False
        for citation in group:
            normalized_citation = _normalize(citation)
            article_match = re.fullmatch(r"dieu\s+(\d+)", normalized_citation)
            if article_match:
                article_number = article_match.group(1)
                found = bool(re.search(rf"\bdieu\s+{article_number}\b", text))
            else:
                found = normalized_citation in text
            if found:
                break
        if not found:
            return False
    return True


_AMOUNT_TOKEN = re.compile(
    r"(?<![\w/])(?P<number>\d[\d., ]*)(?:\s*(?P<unit>trieu|million))?",
    re.IGNORECASE,
)
_RANGE_CONNECTOR = re.compile(r"\s*(?:-|–|den|toi)\s*", re.IGNORECASE)


def _extract_vnd_amounts(answer: str) -> set[int]:
    """Đọc số tiền dạng 5.000.000 đồng, 5-10 triệu hoặc 5 triệu đến 10 triệu."""
    text = _normalize(answer)
    matches = list(_AMOUNT_TOKEN.finditer(text))
    amounts: set[int] = set()

    for index, match in enumerate(matches):
        raw_number = re.sub(r"[^\d]", "", match.group("number"))
        if not raw_number:
            continue
        value = int(raw_number)
        has_million_unit = bool(match.group("unit"))

        # Trong cách ghi "5-10 triệu", đơn vị ở đầu mút thứ hai áp dụng cho cả khoảng.
        if not has_million_unit and index + 1 < len(matches):
            next_match = matches[index + 1]
            gap = text[match.end() : next_match.start()]
            if (
                _RANGE_CONNECTOR.fullmatch(gap)
                and next_match.group("unit")
                and not re.search(r"\d", gap)
            ):
                has_million_unit = True

        if has_million_unit:
            value *= 1_000_000
        # Bỏ số Điều, tuổi và số hiệu văn bản; chỉ chấm số tiền có quy mô VND hợp lý.
        if value >= 100_000:
            amounts.add(value)

    return amounts


_SUBJECT_PATTERNS = {
    "organization": re.compile(r"\b(?:to chuc|cong ty|doanh nghiep|phap nhan)\b"),
    "individual": re.compile(r"\b(?:ca nhan|nhan vien|hoc sinh|nguoi vi pham)\b"),
    "player": re.compile(r"\b(?:nguoi choi|ca nhan|game thu)\b"),
}
_ANY_SUBJECT = re.compile(
    r"\b(?:to chuc|cong ty|doanh nghiep|phap nhan|ca nhan|nhan vien|hoc sinh|"
    r"nguoi vi pham|nguoi choi|game thu)\b"
)


_COMPARISON_REF = re.compile(
    r"(?:1/2|mot nua|gap doi|bang|nhu|so voi)\s+(?:muc\s+phat\s+(?:tien\s+)?)?"
    r"(?:doi\s+voi\s+|cua\s+)?(?:to chuc|cong ty|doanh nghiep|ca nhan)",
    re.IGNORECASE,
)


def _subject_segments(answer: str) -> list[tuple[str, str]]:
    """Gắn phần nội dung sau mỗi nhãn chủ thể với nhãn gần nhất phía trước,
    bỏ qua các cụm so sánh công thức (VD: 'bằng 1/2 mức phạt của tổ chức') để tránh tách sai."""
    text = _COMPARISON_REF.sub(" ", _normalize(answer))
    lines = [ln.strip() for ln in re.split(r"[\n;|]+", text) if ln.strip()]
    result: list[tuple[str, str]] = []
    for idx, line in enumerate(lines):
        positions = list(_ANY_SUBJECT.finditer(line))
        # Nếu dòng tiêu đề chứa chủ thể (VD: "Đối với Tổ chức:") còn số tiền nằm ở dòng con kế tiếp
        tail_context = ""
        for next_line in lines[idx + 1 : idx + 3]:
            if _ANY_SUBJECT.search(next_line):
                break
            tail_context += " " + next_line
        full_line = line + tail_context
        for index, match in enumerate(positions):
            end = positions[index + 1].start() if index + 1 < len(positions) else len(full_line)
            result.append((match.group(0), full_line[match.end() : end]))
            if index + 1 < len(positions) and (positions[index + 1].start() - match.end()) <= 20:
                next_end = positions[index + 2].start() if index + 2 < len(positions) else len(full_line)
                result.append((match.group(0), full_line[match.end() : next_end]))
    return result


def _subject_is_correct(answer: str, case: dict) -> bool:
    text = _normalize(answer)
    for group in case.get("subject_groups", []):
        if not any(_normalize(marker) in text for marker in group):
            return False

    requirements = case.get("subject_amounts", [])
    if not requirements:
        return True

    segments = _subject_segments(answer)
    for requirement in requirements:
        pattern = _SUBJECT_PATTERNS[requirement["subject"]]
        matching_segments = [
            segment
            for label, segment in segments
            if pattern.fullmatch(label)
        ]
        if not any(set(requirement["amounts"]).issubset(_extract_vnd_amounts(segment))
                   for segment in matching_segments):
            return False
    return True


def _fine_or_age_is_correct(answer: str, case: dict) -> bool:
    rule = case.get("fine_rule")
    if rule == "age_14_16":
        text = _normalize(answer)
        age_is_correct = _contains_any(
            text,
            ["15 tuổi", "từ đủ 14 đến dưới 16 tuổi", "14 đến dưới 16 tuổi"],
        )
        no_fine = _contains_any(
            text,
            [
                "không phạt tiền",
                "không áp dụng phạt tiền",
                "không bị phạt tiền",
                "không phải nộp phạt tiền",
                "không áp dụng hình phạt tiền",
                "chỉ bị cảnh cáo",
                "chỉ áp dụng cảnh cáo",
            ],
        )
        return age_is_correct and no_fine

    if rule == "no_fabricated_fine":
        return not _extract_vnd_amounts(answer)

    expected_amounts = set(case.get("required_amounts", []))
    return expected_amounts.issubset(_extract_vnd_amounts(answer))


def evaluate_answer(answer: str, case: dict) -> tuple[bool, bool, bool]:
    """Trả về (trích dẫn đúng, mức phạt/độ tuổi đúng, chủ thể/guardrail đúng)."""
    return (
        _has_citations(answer, case),
        _fine_or_age_is_correct(answer, case),
        _subject_is_correct(answer, case),
    )


def _rate(rows: list[dict], key: str) -> float:
    return sum(row[key] for row in rows) / len(rows) * 100 if rows else 0.0


async def run_benchmark():
    print("=" * 92)
    print(" THỰC NGHIỆM ĐỐI CHỨNG: NAIVE VECTOR RAG vs. NEURO-SYMBOLIC HYBRID RAG")
    print("=" * 92)

    rows = []
    for case in BENCHMARK_CASES:
        req = ChatRequest(question=case["question"], comparison_mode=True)
        t0 = time.time()
        res = await chat_endpoint(req)
        elapsed = time.time() - t0

        hybrid = evaluate_answer(res.get("answer", ""), case)
        naive = evaluate_answer(res.get("naive_answer") or "", case)
        row = {
            "id": case["id"],
            "category": case["category"],
            "elapsed_seconds": elapsed,
            "h_citation": hybrid[0],
            "h_fine_age": hybrid[1],
            "h_subject_guardrail": hybrid[2],
            "n_citation": naive[0],
            "n_fine_age": naive[1],
            "n_subject_guardrail": naive[2],
        }
        rows.append(row)

        print(f"\n[{case['id']}] {case['category']} ({elapsed:.2f}s)")
        print(
            "  - Neuro-Symbolic : "
            f"Trích dẫn={'✅' if hybrid[0] else '❌'} | "
            f"Mức phạt/độ tuổi={'✅' if hybrid[1] else '❌'} | "
            f"Chủ thể/guardrail={'✅' if hybrid[2] else '❌'}"
        )
        print(
            "  - Naive Vector   : "
            f"Trích dẫn={'✅' if naive[0] else '❌'} | "
            f"Mức phạt/độ tuổi={'✅' if naive[1] else '❌'} | "
            f"Chủ thể/guardrail={'✅' if naive[2] else '❌'}"
        )

    print("\n" + "=" * 92)
    print(" BẢNG TỔNG HỢP KẾT QUẢ ĐỊNH LƯỢNG (DÙNG CHO CHƯƠNG 4 BÁO CÁO)")
    print("=" * 92)
    metrics = [
        ("Citation Accuracy (Trích dẫn đúng)", "citation"),
        ("Fine/Age Accuracy (Mức phạt/độ tuổi)", "fine_age"),
        ("Subject/Guardrail Accuracy (Chủ thể/guardrail)", "subject_guardrail"),
    ]
    for label, key in metrics:
        print(
            f"{label:52}: Naive = {_rate(rows, f'n_{key}'):.1f}% | "
            f"Neuro-Symbolic = {_rate(rows, f'h_{key}'):.1f}%"
        )
    print(f"Số ca đánh giá: {len(rows)}")
    print("=" * 92)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
