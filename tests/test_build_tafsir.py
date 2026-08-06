from pathlib import Path
import re
import unicodedata
import unittest

from pipeline.build_tafsir import (
    QPC_PLACEHOLDER_LETTERS,
    QPC_PLACEHOLDER_RANGES,
    QPC_PLACEHOLDERS,
    QPC_REGION_RE,
    TAG_RE,
    normalize_tafsir_html,
    read_rows,
)


ROOT = Path(__file__).resolve().parents[1]
URDU_TAFSIR_SOURCE = ROOT / "sources" / "tafsir-ibn-kathir-urdu.sqlite"
ENGLISH_TAFSIR_SOURCE = ROOT / "sources" / "tafsir-ibn-kathir-english.sqlite"
# The reader draws `qpc-hafs` text in this face; it lives in the app repo.
QPC_FONT = ROOT.parent / "alquran-app" / "assets" / "fonts" / "UthmanicHafs1-Ver18.ttf"

LETTER_CATEGORIES = {"Lo", "Lu", "Ll"}


def letters_of(html: str) -> list[str]:
    return [
        ch
        for ch in TAG_RE.sub("", html)
        if unicodedata.category(ch) in LETTER_CATEGORIES
    ]


def placeholders_left_in_qpc_regions(html: str) -> list[str]:
    return [
        ch
        for match in QPC_REGION_RE.finditer(html)
        for ch in TAG_RE.sub("", match.group("body"))
        if ord(ch) in QPC_PLACEHOLDERS
    ]


class QpcPlaceholderTableTest(unittest.TestCase):
    """The hard-coded ranges must match the font we actually ship."""

    def test_ranges_match_the_shipped_font(self):
        try:
            from fontTools.pens.recordingPen import RecordingPen
            from fontTools.ttLib import TTFont
        except ImportError:  # pragma: no cover - fontTools is optional locally
            self.skipTest("fontTools not installed")
        if not QPC_FONT.exists():  # pragma: no cover - app repo not checked out
            self.skipTest(f"{QPC_FONT} not available")

        font = TTFont(QPC_FONT)
        cmap: dict[int, str] = {}
        for table in font["cmap"].tables:
            cmap.update(table.cmap)
        glyphs = font.getGlyphSet()

        def outline(name: str) -> tuple:
            pen = RecordingPen()
            glyphs[name].draw(pen)
            return tuple(pen.value)

        # Every codepoint drawn with the same outline as U+060C (ARABIC COMMA) is
        # a placeholder: the font advertises coverage but draws a dotted ring.
        placeholder = outline(cmap[0x060C])
        derived = frozenset(
            cp for cp, glyph in cmap.items() if outline(glyph) == placeholder
        )

        self.assertEqual(derived, QPC_PLACEHOLDERS)

    def test_ranges_are_sorted_and_disjoint(self):
        for (_, prev_end), (next_start, _) in zip(
            QPC_PLACEHOLDER_RANGES, QPC_PLACEHOLDER_RANGES[1:]
        ):
            self.assertLess(prev_end + 1, next_start)


class TafsirNormalizationTest(unittest.TestCase):
    def test_moves_arabic_comma_out_of_inline_quran_span(self):
        html = (
            '<p lang="ur" class="ur">'
            '<span class="arabic qpc-hafs">«مَيْتَةُ، مَوْقُوذَةُ»</span>'
            "</p>"
        )

        normalized = normalize_tafsir_html(html)

        # Comma preserved, but outside the region drawn in KFGQPC Hafs.
        self.assertIn('«مَيْتَةُ</span>،<span class="arabic qpc-hafs"> مَوْقُوذَةُ»', normalized)
        self.assertEqual(placeholders_left_in_qpc_regions(normalized), [])
        self.assertEqual(letters_of(html), letters_of(normalized))

    def test_rescopes_urdu_spelling_instead_of_rewriting_letters(self):
        html = (
            '<p lang="ur" class="ur">اسے نسائی نے '
            '<span class="arabic qpc-hafs"> «عمل الیوم واللیلہ»</span> میں</p>'
        )

        normalized = normalize_tafsir_html(html)

        # Urdu ی / ہ are placeholders in KFGQPC, so the span stops claiming the
        # Qur'anic face — the letters themselves are untouched.
        self.assertIn('<span class="ur" lang="ur"> «عمل الیوم واللیلہ»</span>', normalized)
        self.assertNotIn("qpc-hafs", normalized)
        self.assertEqual(letters_of(html), letters_of(normalized))

    def test_keeps_non_quran_urdu_words_unchanged(self):
        html = (
            '<p lang="ur" class="ur">'
            '<span class="arabic qpc-hafs">«سنگ»</span> '
            '<span class="arabic qpc-hafs">«وقدت الحرب لڑائی»</span>'
            "</p>"
        )

        normalized = normalize_tafsir_html(html)

        self.assertIn("«سنگ»", normalized)
        self.assertIn("«وقدت الحرب لڑائی»", normalized)
        self.assertNotIn("qpc-hafs", normalized)

    def test_block_quran_arabic_keeps_letters_and_drops_pause_marks(self):
        html = (
            '<p class="ar qpc-hafs" lang="ar">'
            "إِنَّ لِكُلِّ شَيْءٍ سَنَامًا، وَإِنَّ سَنَامَ الْقُرْآنِ الْبَقَرَةُ"
            "</p>"
        )

        normalized = normalize_tafsir_html(html)

        # A block is drawn as one run in one font, so the comma cannot be
        # re-scoped out of it — it goes, exactly as the Mushaf sets the text.
        self.assertEqual(
            normalized,
            '<p class="ar qpc-hafs" lang="ar">'
            "إِنَّ لِكُلِّ شَيْءٍ سَنَامًا وَإِنَّ سَنَامَ الْقُرْآنِ الْبَقَرَةُ"
            "</p>",
        )
        self.assertEqual(letters_of(html), letters_of(normalized))

    def test_block_quran_arabic_keeps_the_question(self):
        html = '<p class="ar qpc-hafs" lang="ar">أَتَدْرُونَ مَا هَذَا؟</p>'

        normalized = normalize_tafsir_html(html)

        self.assertIn("مَا هَذَا?", normalized)
        self.assertEqual(placeholders_left_in_qpc_regions(normalized), [])

    def test_folds_presentation_forms_the_font_cannot_draw(self):
        html = '<p class="ar qpc-hafs" lang="ar">سُبْحَانَ ﷲ</p>'

        normalized = normalize_tafsir_html(html)

        self.assertIn("الله", normalized)
        self.assertNotIn("ﷲ", normalized)

    def test_wraps_loose_urdu_heading_before_html_blocks(self):
        html = (
            "تفسیر سورۃ النساء:"
            '<div lang="ur" class="ur"><p class="ur">سیدنا ابن عباس رضی اللہ '
            "عنہما فرماتے ہیں۔</p></div>"
        )

        normalized = normalize_tafsir_html(html)

        self.assertTrue(
            normalized.startswith('<h2 lang="ur" class="ur">تفسیر سورۃ النساء:</h2>')
        )
        self.assertNotIn("تفسیر سورۃ النساء:<div", normalized)


class TafsirCorpusTest(unittest.TestCase):
    """Regression cover over the whole published corpus, not just samples."""

    def _assert_corpus_clean(self, source: Path, language: str) -> None:
        if not source.exists():  # pragma: no cover - sources are not committed
            self.skipTest(f"{source} not available")

        rows = read_rows(source, None)
        self.assertEqual(len(rows), 6236)

        offenders = [
            (row["ayah_key"], "".join(sorted(set(left))))
            for row in rows
            if (left := placeholders_left_in_qpc_regions(row["text"] or ""))
        ]
        self.assertEqual(offenders, [], f"{language}: ◉ placeholders survived")

    def test_english_corpus_has_no_placeholders_in_quran_regions(self):
        self._assert_corpus_clean(ENGLISH_TAFSIR_SOURCE, "en")

    def test_urdu_corpus_has_no_placeholders_in_quran_regions(self):
        self._assert_corpus_clean(URDU_TAFSIR_SOURCE, "ur")

    def test_urdu_corpus_alters_no_arabic_letters(self):
        if not URDU_TAFSIR_SOURCE.exists():  # pragma: no cover
            self.skipTest(f"{URDU_TAFSIR_SOURCE} not available")

        # Presentation forms are the one deliberate letter-level change: they
        # decompose to the same letters (ﷲ -> الله), which the font can draw.
        import sqlite3

        conn = sqlite3.connect(URDU_TAFSIR_SOURCE)
        try:
            changed = [
                key
                for key, text in conn.execute("SELECT ayah_key, text FROM tafsir")
                if text
                and "ﭐ" > max(text, default="")  # no presentation forms present
                and letters_of(text) != letters_of(normalize_tafsir_html(text) or "")
            ]
        finally:
            conn.close()

        self.assertEqual(changed, [])

    def test_no_loose_urdu_headings_survive(self):
        if not URDU_TAFSIR_SOURCE.exists():  # pragma: no cover
            self.skipTest(f"{URDU_TAFSIR_SOURCE} not available")

        loose_heading_re = re.compile(r"^[^<\n]{3,120}:[ \t]*(?=<)")
        rows = read_rows(URDU_TAFSIR_SOURCE, None)
        bad = [
            row["ayah_key"] for row in rows if loose_heading_re.search(row["text"] or "")
        ]

        self.assertEqual(bad, [])


class QpcPlaceholderClassificationTest(unittest.TestCase):
    def test_urdu_letters_are_classified_as_placeholder_letters(self):
        for ch in "یہکھۃےںگپچڈڑژ":
            self.assertIn(ord(ch), QPC_PLACEHOLDER_LETTERS, ch)

    def test_arabic_punctuation_is_not_classified_as_a_letter(self):
        for ch in "،؛؟۔":
            self.assertIn(ord(ch), QPC_PLACEHOLDERS, ch)
            self.assertNotIn(ord(ch), QPC_PLACEHOLDER_LETTERS, ch)

    def test_quran_letters_and_marks_are_never_placeholders(self):
        # Uthmani letters, harakat and waqf signs must stay in the QPC face.
        for ch in "ابتثجحخدذرزسشصضطظعغفقكلمنهوي" "ًَّٰ" "ۖ۝۞":
            self.assertNotIn(ord(ch), QPC_PLACEHOLDERS, hex(ord(ch)))


if __name__ == "__main__":
    unittest.main()
