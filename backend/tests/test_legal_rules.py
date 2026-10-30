from datetime import date
import sys
import unicodedata
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from legal_rules import (
    DECREE_RULES,
    INDIVIDUAL,
    ORGANIZATION,
    analyze_question,
    apply_penalty_rules,
    infer_criminal_escalation,
    requires_out_of_scope_guardrail,
)


class AnalyzeQuestionTests(unittest.TestCase):
    def test_normalizes_nfd_and_defaults_current_cybersecurity_law(self):
        question = unicodedata.normalize("NFD", "Luật An ninh mạng nói gì?")
        facts = analyze_question(question)
        self.assertIn("116/2025/QH15", facts.doc_hints)

    def test_explicit_historical_cybersecurity_law_is_preserved(self):
        facts = analyze_question("Luật An ninh mạng 2018 quy định gì?")
        self.assertEqual(facts.doc_hints, ["24/2018/QH14"])

    def test_current_decrees_are_recognized(self):
        facts = analyze_question("Nghị định 174/2026/NĐ-CP và 330/2026/NĐ-CP")
        self.assertEqual(
            facts.doc_hints,
            ["174/2026/NĐ-CP", "330/2026/NĐ-CP"],
        )

    def test_unknown_full_codes_are_missing_from_corpus_not_nonexistent(self):
        facts = analyze_question("15/2099/NĐ-CP và 22/2026/NĐ-CP")
        self.assertEqual(
            facts.invalid_docs,
            ["Nghị định 15/2099/NĐ-CP", "Nghị định 22/2026/NĐ-CP"],
        )
        self.assertFalse(requires_out_of_scope_guardrail(facts))

    def test_known_traffic_decree_uses_scope_guardrail_even_with_article_number(self):
        facts = analyze_question("Điều 12 Nghị định 100/2019/NĐ-CP về vượt đèn đỏ")
        self.assertEqual(facts.invalid_docs, [])
        self.assertTrue(requires_out_of_scope_guardrail(facts))

    def test_unknown_bare_decree_number_is_not_guessed_as_out_of_scope(self):
        facts = analyze_question("Nghị định 22 quy định gì?")
        self.assertFalse(facts.out_of_scope_docs)
        self.assertTrue(facts.invalid_docs)

    def test_verb_organization_is_not_a_legal_entity(self):
        facts = analyze_question("Tổ chức sự kiện trên mạng có cần xin phép không?")
        self.assertFalse(facts.subject_detected)
        self.assertEqual(set(facts.subjects), {ORGANIZATION, INDIVIDUAL})

    def test_organization_subject_context_is_detected(self):
        facts = analyze_question("Tổ chức vi phạm thì bị xử lý thế nào?")
        self.assertTrue(facts.subject_detected)
        self.assertEqual(facts.subjects, [ORGANIZATION])

    def test_age_of_website_is_not_a_person_age(self):
        facts = analyze_question("Website của công ty đã hoạt động 15 tuổi")
        self.assertIsNone(facts.age)
        self.assertIsNone(facts.age_band)

    def test_under_16_does_not_collapse_to_age_15(self):
        facts = analyze_question("Người vi phạm dưới 16 tuổi")
        self.assertIsNone(facts.age)
        self.assertEqual(facts.age_band, "UNDER_16_UNSPECIFIED")

    def test_under_14_is_kept_as_a_separate_band(self):
        facts = analyze_question("Người vi phạm dưới 14 tuổi")
        self.assertEqual(facts.age, 13)
        self.assertEqual(facts.age_band, "UNDER_14")

    def test_article_suffix_is_preserved(self):
        facts = analyze_question("Nghị định 15/2020/NĐ-CP, Điều 93a")
        self.assertEqual(facts.article_refs, ["93a"])
        self.assertEqual(facts.doc_hints, ["15/2020/NĐ-CP"])


class PenaltyRuleTests(unittest.TestCase):
    def test_only_configured_decree_rules_are_applied(self):
        facts = analyze_question("cá nhân vi phạm")
        # Văn bản Luật (không có trong DECREE_RULES) thì không tự chia đôi tiền phạt
        unsupported = apply_penalty_rules(
            {"type": "FINE", "min_amount": 10_000_000, "max_amount": 20_000_000},
            "20/2023/QH15",
            95,
            facts,
        )
        self.assertFalse(unsupported["rule_supported"])
        self.assertEqual(unsupported["results"], [])

        # Nghị định 174/2026/NĐ-CP đã được cấu hình trong DECREE_RULES
        supported = apply_penalty_rules(
            {"type": "FINE", "min_amount": 20_000_000, "max_amount": 30_000_000},
            "174/2026/NĐ-CP",
            95,
            facts,
        )
        self.assertTrue(supported["rule_supported"])
        self.assertEqual(supported["results"][0]["min_amount"], 10_000_000)

    def test_verified_criminal_escalation_has_code_and_article(self):
        res = infer_criminal_escalation("15/2020/NĐ-CP", 101, "đăng tin sai sự thật")
        self.assertTrue(len(res) > 0)
        self.assertEqual(res[0]["article"], 288)
        self.assertEqual(res[0]["code"], "100/2015/QH13")

    def test_expanded_cybercrime_escalation_articles(self):
        # Điều 285: Công cụ, phần mềm độc hại
        res_285 = infer_criminal_escalation("15/2020/NĐ-CP", 77, "sản xuất công cụ phần mềm độc hại")
        self.assertTrue(len(res_285) > 0)
        self.assertEqual(res_285[0]["article"], 285)

        # Điều 286: Phát tán virus, ransomware
        res_286 = infer_criminal_escalation("15/2020/NĐ-CP", 78, "phát tán virus mã độc tống tiền")
        self.assertTrue(len(res_286) > 0)
        self.assertEqual(res_286[0]["article"], 286)

        # Điều 287: Tấn công DDoS, làm tê liệt mạng
        res_287 = infer_criminal_escalation("15/2020/NĐ-CP", 79, "tấn công ddos gây nghẽn mạng làm tê liệt")
        self.assertTrue(len(res_287) > 0)
        self.assertEqual(res_287[0]["article"], 287)

        # Điều 289: Xâm nhập trái phép, bẻ khóa
        res_289 = infer_criminal_escalation("15/2020/NĐ-CP", 80, "bẻ khóa xâm nhập trái phép chiếm quyền")
        self.assertTrue(len(res_289) > 0)
        self.assertEqual(res_289[0]["article"], 289)

        # Điều 290: Lừa đảo chiếm đoạt tài sản qua mạng
        res_290 = infer_criminal_escalation("15/2020/NĐ-CP", 82, "lừa đảo qua mạng chiếm đoạt tài sản")
        self.assertTrue(len(res_290) > 0)
        self.assertEqual(res_290[0]["article"], 290)

        # Điều 285 & 286 dẫn chiếu từ Luật An ninh mạng 2025 (116/2025/QH15) và chuẩn hóa biến
        res_285_anm2025 = infer_criminal_escalation("116/2025/QH15", "Điều 8", "Mua bán công cụ, phần mềm độc hại")
        self.assertTrue(len(res_285_anm2025) > 0)
        self.assertEqual(res_285_anm2025[0]["article"], 285)

        res_286_anm2025 = infer_criminal_escalation("116/2025/qh15", 7, "Phát tán mã độc ransomware")
        self.assertTrue(len(res_286_anm2025) > 0)
        self.assertEqual(res_286_anm2025[0]["article"], 286)

    def test_decree_15_scope_covers_114_114a_with_100m_individual_cap(self):
        self.assertEqual(DECREE_RULES["15/2020/NĐ-CP"]["scope"], (5, 119))
        facts = analyze_question("Cá nhân vi phạm theo Điều 114a Nghị định 15/2020/NĐ-CP")
        res_114a = apply_penalty_rules(
            {"type": "FINE", "min_amount": 30_000_000, "max_amount": 50_000_000},
            "15/2020/NĐ-CP",
            "114a",
            facts,
        )
        self.assertTrue(res_114a["rule_supported"])
        self.assertEqual(res_114a["results"][0]["min_amount"], 15_000_000)
        self.assertEqual(res_114a["results"][0]["max_amount"], 25_000_000)
        self.assertTrue(any(s["rule"] == "CAP_CHECK" for s in res_114a["steps"]))

        # Kiểm tra trần phạt 100 triệu cho cá nhân ở dải Điều 113-119
        capped_114 = apply_penalty_rules(
            {"type": "FINE", "min_amount": 180_000_000, "max_amount": 240_000_000},
            "15/2020/NĐ-CP",
            114,
            facts,
        )
        self.assertTrue(capped_114["rule_supported"])
        self.assertEqual(capped_114["results"][0]["max_amount"], 100_000_000)

    def test_16_to_17_result_reports_only_the_legal_cap(self):
        facts = analyze_question("Cá nhân 17 tuổi")
        result = apply_penalty_rules(
            {"type": "FINE", "min_amount": 10_000_000, "max_amount": 20_000_000},
            "15/2020/NĐ-CP",
            101,
            facts,
        )
        individual = next(r for r in result["results"] if r["subject"] == INDIVIDUAL)
        self.assertIsNone(individual["min_amount"])
        self.assertEqual(individual["max_amount"], 5_000_000)
        self.assertIn("không quá", individual["display"].lower())

    def test_ambiguous_under_16_requires_exact_age(self):
        facts = analyze_question("Cá nhân dưới 16 tuổi")
        result = apply_penalty_rules(
            {"type": "FINE", "min_amount": 10_000_000, "max_amount": 20_000_000},
            "15/2020/NĐ-CP",
            101,
            facts,
        )
        individual = next(r for r in result["results"] if r["subject"] == INDIVIDUAL)
        self.assertFalse(individual["applicable"])
        self.assertIn("tuổi chính xác", individual["display"].lower())

    def test_unverified_criminal_escalation_is_disabled(self):
        self.assertEqual(infer_criminal_escalation("15/2020/NĐ-CP", 101, "tấn công"), [])

    def test_article_suffix_enters_numeric_penalty_rules(self):
        facts = analyze_question("Cá nhân vi phạm theo Điều 93a")
        result = apply_penalty_rules(
            {"type": "FINE", "min_amount": 20_000_000, "max_amount": 30_000_000},
            "15/2020/NĐ-CP",
            "93a",
            facts,
        )
        self.assertTrue(result["rule_supported"])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["min_amount"], 10_000_000)
        self.assertEqual(result["results"][0]["max_amount"], 15_000_000)

        # Invalid non-numeric string should not be supported
        invalid_res = apply_penalty_rules(
            {"type": "FINE", "min_amount": 20_000_000, "max_amount": 30_000_000},
            "15/2020/NĐ-CP",
            "abc",
            facts,
        )
        self.assertFalse(invalid_res["rule_supported"])


class MainModuleImportTests(unittest.TestCase):
    def test_main_imports_and_symbols_available(self):
        import main
        self.assertIsNotNone(main.ORGANIZATION)
        self.assertIsNotNone(main.DECREE_RULES)
        self.assertIsNotNone(main.query_knowledge_graph)

    def test_blhs_direct_fallback_populates_action_penalty_nodes_and_211_historical_date(self):
        import main
        graph = main._GraphViewBuilder()
        penalty_calcs = []
        rule_steps = []
        matched_actions = []
        q = "Hành vi cố ý phát tán mã độc ransomware làm tê liệt hệ thống bị xử lý hình sự theo Điều 286 Bộ luật Hình sự 2015?"
        facts = analyze_question(q)
        main._apply_blhs_criminal_fallback(facts, q, graph, penalty_calcs, rule_steps, matched_actions)
        gv = graph.to_dict()
        node_types = {n["type"] for n in gv["nodes"]}
        edge_labels = {e["label"] for e in gv["edges"]}
        self.assertIn("Action", node_types)
        self.assertIn("Penalty", node_types)
        self.assertIn("DEFINED_IN", edge_labels)
        self.assertIn("PENALIZED_BY", edge_labels)

        # Kiểm tra 211/2025/NĐ-CP thuộc historical_codes để không bị chặn bởi bộ lọc thời gian
        self.assertIn("211/2025/NĐ-CP", main._HISTORICAL_DOC_CODES)
        facts_211 = analyze_question("Theo Nghị định 211/2025/NĐ-CP về mật mã dân sự")
        resolved = main._resolve_effective_date(None, "Theo Nghị định 211/2025/NĐ-CP", facts_211, date(2026, 10, 30))
        self.assertEqual(resolved, date(2026, 6, 30))

        # Kiểm tra nhận diện số hiệu Nghị định viết tắt "NĐ 15/2020"
        facts_nd15 = analyze_question("Quảng cáo dịch vụ bằng tin nhắn ngoài khoảng thời gian quy định theo Điều 94 NĐ 15/2020?")
        self.assertIn("15/2020/NĐ-CP", facts_nd15.doc_hints)


if __name__ == "__main__":
    unittest.main()
