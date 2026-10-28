import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from legal_parser import (
    Article,
    LegalDocument,
    _is_consolidated_source,
    apply_effective_dates,
    identify_document_by_name,
    load_corpus,
)


class LegalParserMetadataTests(unittest.TestCase):
    def test_current_decree_files_have_registry_entries(self):
        self.assertEqual(
            identify_document_by_name("174-2026-ndcp.docx")["code"],
            "174/2026/NĐ-CP",
        )

    def test_canonical_edition_detection(self):
        self.assertTrue(_is_consolidated_source("Nội-dung-hợp-nhất-Luật-67-2006-QH11.pdf"))
        self.assertFalse(_is_consolidated_source("luat-cong-nghe-thong-tin-67-2006-QH11.pdf"))
        self.assertEqual(
            identify_document_by_name("330-2026-ndcp.docx")["code"],
            "330/2026/NĐ-CP",
        )
        self.assertEqual(
            identify_document_by_name("2022_645_646_08-vbhn-btttt.pdf")["code"],
            "15/2020/NĐ-CP",
        )

    def test_repealed_15_articles_keep_historical_effective_dates(self):
        document = LegalDocument(
            code="15/2020/NĐ-CP",
            title="Nghị định 15/2020",
            short="Nghị định 15/2020/NĐ-CP",
            doc_type="DECREE",
            effective_from="2020-04-15",
            articles=[
                Article("15/2020/NĐ-CP", 101, "", "", "", "source.pdf", 1),
                Article("15/2020/NĐ-CP", 4, "", "", "", "source.pdf", 1),
            ],
        )
        apply_effective_dates(document)
        self.assertEqual(document.articles[0].effective_to, "2026-06-30")
        self.assertEqual(document.articles[0].effective_from, "2020-04-15")
        self.assertIsNone(document.articles[1].effective_to)

    def test_current_decree_files_parse_articles_and_fines(self):
        data_dir = Path(__file__).resolve().parents[2] / "data"
        required_files = ["174-2026-ndcp.docx", "330-2026-ndcp.docx"]
        if not all((data_dir / fn).exists() for fn in required_files):
            self.skipTest("Bỏ qua test vì thiếu tệp nhị phân trong data/")
        documents = {
            doc.code: doc
            for doc in load_corpus(
                data_dir,
                only_sources={"174-2026-ndcp.docx", "330-2026-ndcp.docx"},
            )
        }
        article_174 = next(a for a in documents["174/2026/NĐ-CP"].articles if a.number == 95)
        article_330 = next(a for a in documents["330/2026/NĐ-CP"].articles if a.number == 50)
        self.assertEqual((article_174.clauses[0].fine_min, article_174.clauses[0].fine_max), (20_000_000, 30_000_000))
        self.assertEqual((article_330.clauses[1].fine_min, article_330.clauses[1].fine_max), (30_000_000, 50_000_000))
        self.assertEqual(article_174.effective_from, "2026-07-01")
        self.assertEqual(article_330.effective_from, "2026-08-19")

    def test_official_consolidation_uses_both_parts_and_2025_amendments(self):
        data_dir = Path(__file__).resolve().parents[2] / "data"
        required_files = [
            "2022_643_644_08-vbhn-btttt.pdf",
            "2022_645_646_08-vbhn-btttt.pdf",
        ]
        if not all((data_dir / fn).exists() for fn in required_files):
            self.skipTest("Bỏ qua test vì thiếu tệp nhị phân trong data/")
        document = next(
            doc for doc in load_corpus(
                data_dir,
                only_sources={
                    "2022_643_644_08-vbhn-btttt.pdf",
                    "2022_645_646_08-vbhn-btttt.pdf",
                },
            )
            if doc.code == "15/2020/NĐ-CP"
        )
        by_number = {article.number: article for article in document.articles}
        self.assertIn(124, by_number)
        self.assertEqual(by_number["93a"].effective_from, "2025-09-09")
        self.assertEqual(by_number["93a"].effective_to, "2026-06-30")
        self.assertEqual(by_number["93b"].effective_from, "2025-09-09")
        self.assertEqual(by_number[114].effective_from, "2025-09-09")
        self.assertEqual(by_number["114a"].effective_to, "2026-06-30")
        self.assertEqual(by_number["119a"].effective_to, "2026-06-30")
        self.assertEqual(by_number[124].effective_to, "2026-06-30")
        self.assertIn("211-2025-ndcp.signed.pdf", document.sources)


if __name__ == "__main__":
    unittest.main()
