"""Unit tests for title_block_grid labeled-cell parsing."""
from __future__ import annotations

import unittest

from title_block_grid import (
    LabeledCell,
    TextLine,
    WordSpan,
    _classify_bottom_label,
    _cluster_lines_into_cells,
    _cluster_words_into_lines,
    _find_drawing_name_cell,
    _find_drawing_number_cell,
    _is_plausible_drawing_title,
    _lines_to_labeled_cell,
    _normalize_drawing_number,
)


def _make_title_block_lines(page_w: float = 1000, page_h: float = 800):
    """Simulate bottom-right title block: name above sheet number."""
    name_value = WordSpan(820, 700, 960, 728, 'Interior Elevations', font_size=18)
    name_label = WordSpan(825, 732, 910, 742, 'Drawing Name:', font_size=7)
    sheet_value = WordSpan(850, 758, 930, 788, 'A-212', font_size=22)
    sheet_label = WordSpan(855, 792, 920, 802, 'Drawing No.', font_size=7)
    proj_type = WordSpan(600, 700, 750, 718, 'Tenant Improvement', font_size=12)
    proj_label = WordSpan(605, 722, 680, 732, 'Project Type:', font_size=7)

    words = [name_value, name_label, sheet_value, sheet_label]
    lines = _cluster_words_into_lines(words, y_tol=6)
    cells = _cluster_lines_into_cells(lines, cell_gap=14)
    return page_w, page_h, cells


class TitleBlockGridTests(unittest.TestCase):
    def test_classify_labels(self):
        self.assertEqual(_classify_bottom_label('Drawing No.'), 'drawing_number')
        self.assertEqual(_classify_bottom_label('Drawing Number:'), 'drawing_number')
        self.assertEqual(_classify_bottom_label('Drawing Name:'), 'drawing_name')
        self.assertEqual(_classify_bottom_label('Project Type:'), 'project_type')

    def test_normalize_drawing_number_suffix(self):
        self.assertEqual(_normalize_drawing_number('A-102a'), 'A-102A')
        self.assertEqual(_normalize_drawing_number('A-212'), 'A-212')

    def test_reject_project_type_as_drawing_name(self):
        self.assertFalse(_is_plausible_drawing_title('Tenant Improvement', 'A-212'))
        self.assertTrue(_is_plausible_drawing_title('Interior Elevations', 'A-212'))

    def test_bottom_right_cell_extraction(self):
        page_w, page_h, cells = _make_title_block_lines()
        self.assertGreaterEqual(len(cells), 2)
        sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
        self.assertIsNotNone(sheet_cell)
        self.assertEqual(sheet_cell.label_kind, 'drawing_number')
        self.assertEqual(_normalize_drawing_number(sheet_cell.value_text), 'A-212')

        name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
        self.assertIsNotNone(name_cell)
        self.assertEqual(name_cell.label_kind, 'drawing_name')
        self.assertEqual(name_cell.value_text, 'Interior Elevations')

    def test_value_above_label_in_cell(self):
        lines = [
            TextLine(100, 120, 80, 200, 'A-212', [], 28, 22),
            TextLine(130, 140, 80, 180, 'Drawing No.', [], 10, 7),
        ]
        cell = _lines_to_labeled_cell(lines, med_h=12, med_size=10)
        self.assertIsNotNone(cell)
        self.assertEqual(cell.label_kind, 'drawing_number')
        self.assertEqual(cell.value_text, 'A-212')


if __name__ == '__main__':
    unittest.main()
