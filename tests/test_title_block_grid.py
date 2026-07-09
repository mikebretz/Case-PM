"""Unit tests for title_block_grid labeled-cell parsing."""
from __future__ import annotations

import unittest

from title_block_grid import (
    TextLine,
    WordSpan,
    _build_title_block,
    _classify_bottom_label,
    _cluster_lines_into_cells,
    _cluster_words_into_lines,
    _find_drawing_name_cell,
    _find_drawing_number_cell,
    _is_plausible_drawing_title,
    _lines_to_labeled_cell,
    _normalize_drawing_number,
    _split_line_by_columns,
)


class FakePage:
    """Minimal page stub for _build_title_block."""

    def __init__(self, words: list[WordSpan], width: float = 1000, height: float = 800):
        self.rect = type('R', (), {'width': width, 'height': height})()
        self._words = words

    def get_text(self, mode='dict'):
        if mode == 'words':
            return [
                [w.x0, w.y0, w.x1, w.y1, w.text, w.block, w.line]
                for w in self._words
            ]
        return {'blocks': []} if mode == 'dict' else ''

    def get_drawings(self):
        return []


def _make_narrow_stack():
    """A-212 / Interior Elevations in narrow right column."""
    name_value = WordSpan(820, 700, 960, 728, 'Interior Elevations', font_size=18)
    name_label = WordSpan(825, 732, 910, 742, 'Drawing Name:', font_size=7)
    sheet_value = WordSpan(850, 758, 930, 788, 'A-212', font_size=22)
    sheet_label = WordSpan(855, 792, 920, 802, 'Drawing No.', font_size=7)
    words = [name_value, name_label, sheet_value, sheet_label]
    lines = _cluster_words_into_lines(words, y_tol=6)
    for ln in lines:
        ln.column = 'right'
    cells = _cluster_lines_into_cells(lines, cell_gap=14)
    return 1000, 800, cells


def _make_full_title_block():
    """A-201 / Exterior Elevations with left metadata + full-width name band."""
    words = [
        WordSpan(480, 620, 720, 648, 'Exterior Elevations', font_size=20),
        WordSpan(485, 652, 570, 662, 'Drawing Name:', font_size=7),
        WordSpan(490, 680, 580, 692, 'Date:', font_size=7),
        WordSpan(590, 680, 660, 692, '05/23/25', font_size=9),
        WordSpan(490, 700, 560, 712, 'Type:', font_size=7),
        WordSpan(590, 700, 660, 712, 'RETROFIT', font_size=9),
        WordSpan(490, 720, 590, 732, 'Drawn By:', font_size=7),
        WordSpan(600, 720, 630, 732, 'AM', font_size=9),
        WordSpan(700, 680, 770, 692, 'Project No.', font_size=7),
        WordSpan(700, 698, 790, 718, '2024.0565', font_size=16),
        WordSpan(720, 748, 800, 778, 'A-201', font_size=24),
        WordSpan(725, 782, 790, 792, 'Drawing No.', font_size=7),
    ]
    page = FakePage(words)
    return _build_title_block(page)


class TitleBlockGridTests(unittest.TestCase):
    def test_classify_labels(self):
        self.assertEqual(_classify_bottom_label('Drawing No.'), 'drawing_number')
        self.assertEqual(_classify_bottom_label('Drawing Name:'), 'drawing_name')

    def test_normalize_drawing_number(self):
        self.assertEqual(_normalize_drawing_number('A-102a'), 'A-102A')
        self.assertEqual(_normalize_drawing_number('A-201'), 'A-201')

    def test_reject_metadata_as_drawing_name(self):
        self.assertFalse(_is_plausible_drawing_title('RETROFIT', 'A-201'))
        self.assertFalse(_is_plausible_drawing_title('Tenant Improvement', 'A-212'))
        self.assertTrue(_is_plausible_drawing_title('Exterior Elevations', 'A-201'))
        self.assertTrue(_is_plausible_drawing_title('Interior Elevations', 'A-212'))

    def test_narrow_column_stack(self):
        page_w, page_h, cells = _make_narrow_stack()
        sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
        self.assertIsNotNone(sheet_cell)
        self.assertEqual(_normalize_drawing_number(sheet_cell.value_text), 'A-212')
        name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
        self.assertIsNotNone(name_cell)
        self.assertEqual(name_cell.value_text, 'Interior Elevations')

    def test_full_width_name_band(self):
        page_w, page_h, cells = _make_full_title_block()
        self.assertGreaterEqual(len(cells), 2)
        sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
        self.assertIsNotNone(sheet_cell)
        self.assertEqual(sheet_cell.label_kind, 'drawing_number')
        self.assertEqual(_normalize_drawing_number(sheet_cell.value_text), 'A-201')

        name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
        self.assertIsNotNone(name_cell)
        self.assertEqual(name_cell.label_kind, 'drawing_name')
        self.assertEqual(name_cell.value_text, 'Exterior Elevations')

    def test_split_line_by_columns(self):
        left_w = WordSpan(500, 700, 540, 712, 'Type:', font_size=7)
        right_w = WordSpan(700, 700, 760, 712, 'Project No.', font_size=7)
        line = _cluster_words_into_lines([left_w, right_w], y_tol=4)[0]
        parts = _split_line_by_columns(line, 650)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].column, 'left')
        self.assertEqual(parts[1].column, 'right')

    def test_value_above_label_in_cell(self):
        lines = [
            TextLine(100, 120, 80, 200, 'A-212', [], 28, 22, 'right'),
            TextLine(130, 140, 80, 180, 'Drawing No.', [], 10, 7, 'right'),
        ]
        cell = _lines_to_labeled_cell(lines, med_h=12, med_size=10)
        self.assertIsNotNone(cell)
        self.assertEqual(cell.label_kind, 'drawing_number')
        self.assertEqual(cell.value_text, 'A-212')


if __name__ == '__main__':
    unittest.main()
