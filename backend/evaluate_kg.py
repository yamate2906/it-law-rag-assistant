"""Score saved chat responses against a manually reviewed legal QA manifest.

This evaluator is offline and does not call an LLM. Gold records must be reviewed
by a legal-domain annotator; no fabricated gold answers are bundled.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


def _read_records(path: Path, key: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get(key, []) if isinstance(payload, dict) else payload
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise ValueError(f"{path} must contain a list of {key}")
    ids = [item.get("id") for item in records]
    if any(not record_id for record_id in ids) or len(ids) != len(set(ids)):
        raise ValueError(f"{path} contains missing or duplicate record ids")
    return records


def _source_ids(response: dict[str, Any]) -> set[str]:
    return {
        str(source["source_id"])
        for source in response.get("sources", [])
        if isinstance(source, dict) and source.get("source_id")
    }


def _path_edges(response: dict[str, Any]) -> set[tuple[str, str, str]]:
    reasoning = response.get("symbolic_reasoning") or {}
    found: set[tuple[str, str, str]] = set()
    for path in reasoning.get("law_paths", []) or []:
        for edge in path.get("edges", []) or []:
            if edge.get("source") and edge.get("target") and edge.get("type"):
                found.add((str(edge["source"]), str(edge["type"]), str(edge["target"])))
    return found


def evaluate(cases: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    prediction_by_id = {str(item["id"]): item for item in predictions}
    matched = []
    citation_counts = Counter()
    path_exact = []
    temporal_exact = []
    abstention_counts = Counter()
    missing = []

    for case in cases:
        case_id = str(case["id"])
        prediction = prediction_by_id.get(case_id)
        if prediction is None:
            missing.append(case_id)
            continue
        response = prediction.get("response", prediction)
        expected_sources = {str(value) for value in case.get("expected_source_ids", [])}
        predicted_sources = _source_ids(response)
        citation_counts["true_positive"] += len(expected_sources & predicted_sources)
        citation_counts["false_positive"] += len(predicted_sources - expected_sources)
        citation_counts["false_negative"] += len(expected_sources - predicted_sources)

        expected_edges = {
            (str(edge["source"]), str(edge["type"]), str(edge["target"]))
            for edge in case.get("expected_path_edges", [])
        }
        predicted_edges = _path_edges(response)
        path_exact.append(expected_edges == predicted_edges if expected_edges else not predicted_edges)

        expected_date = case.get("as_of_date")
        predicted_date = response.get("effective_as_of") or (response.get("symbolic_reasoning") or {}).get("as_of_date")
        temporal_exact.append(expected_date is None or expected_date == predicted_date)

        # This checks the backend evidence gate, not whether an LLM's prose truly abstained.
        should_abstain = bool(case.get("should_abstain", False))
        evidence_state = response.get("evidence_state", "NO_EVIDENCE")
        did_abstain = evidence_state in {"NO_EVIDENCE", "TEMPORAL_STATUS_ONLY"}
        abstention_counts["correct"] += int(should_abstain == did_abstain)
        abstention_counts["false_abstain"] += int(did_abstain and not should_abstain)
        abstention_counts["missed_abstain"] += int(should_abstain and not did_abstain)
        matched.append(case_id)

    tp = citation_counts["true_positive"]
    fp = citation_counts["false_positive"]
    fn = citation_counts["false_negative"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "cases_scored": len(matched),
        "missing_predictions": missing,
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "path_exact_match": sum(path_exact) / len(path_exact) if path_exact else None,
        "temporal_accuracy": sum(temporal_exact) / len(temporal_exact) if temporal_exact else None,
        "evidence_gate_abstention_accuracy": abstention_counts["correct"] / len(matched) if matched else None,
        "false_evidence_gate_abstentions": abstention_counts["false_abstain"],
        "missed_evidence_gate_abstentions": abstention_counts["missed_abstain"],
        "matched_case_ids": matched,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chấm citation/path/temporal trên bộ QA pháp lý đã gán nhãn")
    parser.add_argument("--cases", required=True, type=Path, help="Manifest chuẩn đã được người có chuyên môn duyệt")
    parser.add_argument("--predictions", required=True, type=Path, help="JSON response đã lưu theo id của case")
    parser.add_argument("--output", type=Path, help="File JSON kết quả; mặc định in ra stdout")
    args = parser.parse_args(argv)

    result = evaluate(_read_records(args.cases, "cases"), _read_records(args.predictions, "predictions"))
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
