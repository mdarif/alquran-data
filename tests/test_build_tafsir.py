from pathlib import Path
import re
import unittest

from pipeline.build_tafsir import (
    QPC_SPAN_RE,
    QURAN_SEPARATOR_RE,
    URDU_SPECIFIC_RE,
    normalize_tafsir_html,
    read_rows,
)


ROOT = Path(__file__).resolve().parents[1]
URDU_TAFSIR_SOURCE = ROOT / "sources" / "tafsir-ibn-kathir-urdu.sqlite"


class TafsirNormalizationTest(unittest.TestCase):
    def test_normalizes_quran_arabic_span_codepoints(self):
        html = (
            '<p lang="ur" class="ur">اس میں آیت '
            '<span class="arabic qpc-hafs">«يٰٓاَيُّھَا الَّذِيْنَ اٰمَنُوْٓا '
            "اَوْفُوْا بِالْعُقُوْدِ»</span></p>"
        )

        normalized = normalize_tafsir_html(html)

        self.assertIn("«يٰٓاَيُّهَا", normalized)
        self.assertNotIn("يٰٓاَيُّھَا", normalized)

    def test_keeps_non_quran_urdu_words_unchanged(self):
        html = (
            '<p lang="ur" class="ur">'
            '<span class="arabic qpc-hafs">«سنگ»</span> '
            '<span class="arabic qpc-hafs">«گل»</span> '
            '<span class="arabic qpc-hafs">«وقدت الحرب لڑائی»</span>'
            "</p>"
        )

        normalized = normalize_tafsir_html(html)

        self.assertIn("«سنگ»", normalized)
        self.assertIn("«گل»", normalized)
        self.assertIn("«وقدت الحرب لڑائی»", normalized)
        self.assertNotIn('class="arabic qpc-hafs">«سنگ»', normalized)
        self.assertNotIn('class="arabic qpc-hafs">«گل»', normalized)

    def test_moves_separators_out_of_quran_spans(self):
        html = (
            '<p lang="ur" class="ur">'
            '<span class="arabic qpc-hafs">«مَيْتَةُ، مَوْقُوذَةُ، '
            'مُتَرَدِّيَةُ، لنَّطِيحَةُ»</span>'
            "</p>"
        )

        normalized = normalize_tafsir_html(html)

        self.assertIn("</span>،<span", normalized)
        self.assertNotIn("مَيْتَةُ، مَوْقُوذَةُ", normalized)
        self.assertIn('class="arabic qpc-hafs">«مَيْتَةُ</span>', normalized)
        self.assertIn('class="arabic qpc-hafs"> مَوْقُوذَةُ</span>', normalized)

    def test_wraps_loose_urdu_heading_before_html_blocks(self):
        html = (
            'تفسیر سورۃ النساء:'
            '<div lang="ur" class="ur"><p class="ur">سیدنا ابن عباس رضی اللہ '
            'عنہما فرماتے ہیں۔</p></div>'
        )

        normalized = normalize_tafsir_html(html)

        self.assertTrue(
            normalized.startswith('<h2 lang="ur" class="ur">تفسیر سورۃ النساء:</h2>')
        )
        self.assertNotIn('تفسیر سورۃ النساء:<div', normalized)

    def test_full_urdu_tafsir_source_has_clean_qpc_spans_and_headings(self):
        rows = read_rows(URDU_TAFSIR_SOURCE, None)
        self.assertEqual(len(rows), 6236)

        bad_qpc_spans = []
        bad_separators = []
        bad_loose_headings = []
        loose_heading_re = re.compile(r"^[^<\n]{3,120}:[ \t]*(?=<)")

        for row in rows:
            text = row["text"] or ""
            for match in QPC_SPAN_RE.finditer(text):
                body = re.sub(r"<[^>]+>", "", match.group(2))
                if URDU_SPECIFIC_RE.search(body):
                    bad_qpc_spans.append((row["ayah_key"], body))
                if QURAN_SEPARATOR_RE.search(body):
                    bad_separators.append((row["ayah_key"], body))
            if loose_heading_re.search(text):
                bad_loose_headings.append(row["ayah_key"])

        self.assertEqual(bad_qpc_spans, [])
        self.assertEqual(bad_separators, [])
        self.assertEqual(bad_loose_headings, [])


if __name__ == "__main__":
    unittest.main()
