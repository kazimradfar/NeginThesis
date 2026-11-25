import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_thesis as ct  # noqa: E402

P = ct.Paragraph


def doc(*items):
    """Build a tiny fake document: a heading, body text, then a reference list."""
    return list(items)


class ExpandCitation(unittest.TestCase):
    def test_single(self):
        self.assertEqual(ct.expand_citation("5"), [5])

    def test_list(self):
        self.assertEqual(ct.expand_citation("7, 12"), [7, 12])

    def test_range_hyphen_and_en_dash(self):
        self.assertEqual(ct.expand_citation("3-5"), [3, 4, 5])
        self.assertEqual(ct.expand_citation("3–5"), [3, 4, 5])

    def test_mixed(self):
        self.assertEqual(ct.expand_citation("1, 3-4"), [1, 3, 4])


class Analyse(unittest.TestCase):
    def setUp(self):
        self.paragraphs = doc(
            P("Heading1", "Introduction"),
            P("", "TBI is used before transplantation (1). Doses are uniform (3-4). "
                  "Equation (2.1) is not a citation. Pending [TO BE CONFIRMED: phantom model]."),
            P("Heading2", "Results"),
            P("", "Table 4.1 (green = expected values, replace with measured data)."),
            P("Heading1", "References"),
            P("EndNoteBibliography", "1.Alpha A. First paper title here. J Test. 2000."),
            P("EndNoteBibliography", "2.Beta B. Second paper title here. J Test. 2001."),
            P("EndNoteBibliography", "3.Gamma C. Third paper title here. J Test. 2002."),
        )

    def test_missing_uncited_and_counts(self):
        r = ct.analyse(self.paragraphs)
        self.assertEqual(r["n_references"], 3)
        self.assertEqual(r["missing"], [4])      # (3-4) cites a non-existent ref 4
        self.assertEqual(r["uncited"], [2])      # ref 2 is never cited
        self.assertEqual(r["cited_numbers"], [1, 3, 4])

    def test_equation_number_is_not_a_citation(self):
        r = ct.analyse(self.paragraphs)
        self.assertNotIn(2, r["cited_numbers"])

    def test_placeholders_and_expected_values_grouped_by_section(self):
        r = ct.analyse(self.paragraphs)
        self.assertEqual(len(r["placeholders"]), 1)
        self.assertEqual(r["placeholders"][0][0], "Introduction")
        self.assertEqual(r["expected"][0][0], "Introduction > Results")

    def test_out_of_order(self):
        paragraphs = doc(
            P("Heading1", "Intro"),
            P("", "First (3), then (1)."),
            P("Heading1", "References"),
            P("EndNoteBibliography", "1.A. One. J. 2000."),
            P("EndNoteBibliography", "2.B. Two. J. 2001."),
            P("EndNoteBibliography", "3.C. Three. J. 2002."),
        )
        r = ct.analyse(paragraphs)
        self.assertEqual([x[0] for x in r["out_of_order"]], [1])

    def test_gap_in_numbering_and_duplicates(self):
        paragraphs = doc(
            P("", "Cited (1) and (3)."),
            P("Heading1", "References"),
            P("EndNoteBibliography", "1.Same Author. An identical reference title used twice here. J. 2000."),
            P("EndNoteBibliography", "3.Same Author. An identical reference title used twice here. J. 2000."),
        )
        r = ct.analyse(paragraphs)
        self.assertEqual(r["gaps"], [2])
        self.assertEqual(r["duplicates"], [(1, 3)])

    def test_same_author_different_reports_are_not_duplicates(self):
        paragraphs = doc(
            P("", "Cited (1), (2) and (3)."),
            P("Heading1", "References"),
            P("EndNoteBibliography", "1.International Commission on Radiation Units and Measurements. "
                                     "ICRU Report 83: prescribing, recording, and reporting photon-beam IMRT. 2010."),
            P("EndNoteBibliography", "2.International Commission on Radiation Units and Measurements. "
                                     "ICRU Report 48: phantoms and computational models in therapy. Bethesda: ICRU; 1992."),
            P("EndNoteBibliography", "3.International Commission on Radiation Units and Measurements. "
                                     "ICRU Report 44: tissue substitutes in radiation dosimetry. Bethesda: ICRU; 1989."),
        )
        self.assertEqual(ct.analyse(paragraphs)["duplicates"], [])

    def test_counts_marks_not_expanded_numbers(self):
        paragraphs = doc(P("", "Range (3-5) and list (1, 2)."), P("Heading1", "References"))
        r = ct.analyse(paragraphs)
        self.assertEqual(r["n_citation_marks"], 2)
        self.assertEqual(r["cited_numbers"], [1, 2, 3, 4, 5])

    def test_ris_comparison(self):
        ris = [
            {"TI": "First paper title here", "AU": ["Alpha, A."], "PY": "2000"},
            {"TI": "A paper that is not in the draft", "AU": ["Delta, D."], "PY": "2010"},
        ]
        r = ct.analyse(self.paragraphs, ris)
        self.assertEqual(len(r["ris_missing_in_draft"]), 1)
        self.assertEqual(r["draft_missing_in_ris"], [2, 3])

    def test_errors_and_warnings(self):
        errors, warnings = ct.errors_and_warnings(ct.analyse(self.paragraphs))
        self.assertEqual(errors, 1)
        self.assertGreater(warnings, 0)


class Report(unittest.TestCase):
    def test_render_has_summary_table(self):
        text = ct.render(ct.analyse([P("", "Nothing cited."), P("Heading1", "References")]))
        self.assertIn("# Thesis check report", text)
        self.assertIn("| Check | Result |", text)

    def test_persian_report_is_right_to_left_and_translated(self):
        paragraphs = doc(
            P("Heading1", "Intro"),
            P("", "Cited (1) and (4). Pending [TO BE CONFIRMED: model]."),
            P("Heading1", "References"),
            P("EndNoteBibliography", "1.Alpha A. First paper title here. J Test. 2000."),
        )
        text = ct.render(ct.analyse(paragraphs), "fa")
        self.assertTrue(text.startswith('<div dir="rtl"'))
        self.assertTrue(text.rstrip().endswith("</div>"))
        self.assertIn("گزارش بررسی پایان‌نامه", text)
        self.assertIn("| بررسی | نتیجه |", text)
        self.assertIn("منبع شماره 4 وجود ندارد", text)   # the missing-reference line
        self.assertIn("[TO BE CONFIRMED: model]", text)    # markers stay as written
        self.assertNotIn("Thesis check report", text)

    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(set(ct.STRINGS["en"]), set(ct.STRINGS["fa"]))


if __name__ == "__main__":
    unittest.main()
