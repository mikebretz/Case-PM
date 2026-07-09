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
    _extract_by_label_proximity,
    _find_drawing_name_cell,
    _find_drawing_number_cell,
    _is_plausible_drawing_title,
    _lines_to_labeled_cell,
    _normalize_drawing_number,
    _split_line_by_columns,
    _title_block_lines_from_page,
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


def _make_full_title_block(sheet: str = 'A-201'):
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
        WordSpan(720, 748, 800, 778, sheet, font_size=24),
        WordSpan(725, 782, 790, 792, 'Drawing No.', font_size=7),
    ]
    return FakePage(words)


def _make_window_elevations_block():
    words = [
        WordSpan(480, 580, 760, 608, 'Window Elevations & Details', font_size=20),
        WordSpan(485, 612, 570, 622, 'Drawing Name:', font_size=7),
        WordSpan(700, 640, 770, 652, 'Project No.', font_size=7),
        WordSpan(700, 658, 790, 678, '2024.0565', font_size=16),
        WordSpan(720, 700, 800, 730, 'A-602', font_size=24),
        WordSpan(725, 734, 790, 744, 'Drawing No.', font_size=7),
        WordSpan(420, 760, 700, 772, 'AGUMOA - 06/04/2026 3:11:00 PM', font_size=8),
    ]
    return FakePage(words)


def _make_lighting_block():
    words = [
        WordSpan(480, 560, 700, 582, 'Lighting Schedules', font_size=18),
        WordSpan(480, 586, 620, 608, 'and Diagrams', font_size=18),
        WordSpan(485, 612, 570, 622, 'Drawing Name:', font_size=7),
        WordSpan(700, 640, 770, 652, 'Project No.', font_size=7),
        WordSpan(700, 658, 790, 678, '2024.0565', font_size=16),
        WordSpan(720, 700, 800, 730, 'E-102', font_size=24),
        WordSpan(725, 734, 790, 744, 'Drawing No.', font_size=7),
    ]
    return FakePage(words)


def _make_fire_alarm_block():
    words = [
        WordSpan(480, 600, 680, 622, 'Fire Alarm', font_size=18),
        WordSpan(480, 628, 720, 650, 'Conduit Plan', font_size=18),
        WordSpan(485, 652, 570, 662, 'Drawing Name:', font_size=7),
        WordSpan(700, 680, 770, 692, 'Project No.', font_size=7),
        WordSpan(700, 698, 790, 718, '2024.0565', font_size=16),
        WordSpan(710, 748, 820, 778, 'CLP-101b', font_size=24),
        WordSpan(725, 782, 790, 792, 'Drawing No.', font_size=7),
    ]
    return FakePage(words)


class TitleBlockGridTests(unittest.TestCase):
    def test_classify_labels(self):
        self.assertEqual(_classify_bottom_label('Drawing No.'), 'drawing_number')
        self.assertEqual(_classify_bottom_label('Drawing Name:'), 'drawing_name')

    def test_normalize_drawing_number(self):
        self.assertEqual(_normalize_drawing_number('A-102a'), 'A-102A')
        self.assertEqual(_normalize_drawing_number('A-201'), 'A-201')
        self.assertEqual(_normalize_drawing_number('CLP-101b'), 'CLP-101B')
        self.assertEqual(_normalize_drawing_number('A-202'), 'A-202')

    def test_reject_metadata_as_drawing_name(self):
        self.assertFalse(_is_plausible_drawing_title('RETROFIT', 'A-201'))
        self.assertTrue(_is_plausible_drawing_title('Exterior Elevations', 'A-202'))
        self.assertTrue(_is_plausible_drawing_title('Fire Alarm Conduit Plan', 'CLP-101B'))

    def test_label_proximity_a202(self):
        page = _make_full_title_block('A-202')
        pw, ph, lines, med = _title_block_lines_from_page(page)
        prox = _extract_by_label_proximity(lines, pw, ph, med)
        self.assertEqual(prox['sheet_number'], 'A-202')
        self.assertEqual(prox['drawing_name'], 'Exterior Elevations')

    def test_label_proximity_a602_window(self):
        page = _make_window_elevations_block()
        pw, ph, lines, med = _title_block_lines_from_page(page)
        prox = _extract_by_label_proximity(lines, pw, ph, med)
        self.assertEqual(prox['sheet_number'], 'A-602')
        self.assertEqual(prox['drawing_name'], 'Window Elevations & Details')

    def test_label_proximity_e102_lighting(self):
        page = _make_lighting_block()
        pw, ph, lines, med = _title_block_lines_from_page(page)
        prox = _extract_by_label_proximity(lines, pw, ph, med)
        self.assertEqual(prox['sheet_number'], 'E-102')
        self.assertEqual(prox['drawing_name'], 'Lighting Schedules and Diagrams')
        self.assertTrue(prox.get('label_anchored'))

    def test_label_proximity_clp_fire_alarm(self):
        page = _make_fire_alarm_block()
        pw, ph, lines, med = _title_block_lines_from_page(page)
        prox = _extract_by_label_proximity(lines, pw, ph, med)
        self.assertEqual(prox['sheet_number'], 'CLP-101B')
        self.assertEqual(prox['drawing_name'], 'Fire Alarm Conduit Plan')

    def test_narrow_column_stack(self):
        page_w, page_h, cells = _make_narrow_stack()
        sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
        self.assertEqual(_normalize_drawing_number(sheet_cell.value_text), 'A-212')

    def test_full_width_name_band(self):
        page = _make_full_title_block('A-201')
        page_w, page_h, cells = _build_title_block(page)
        sheet_cell = _find_drawing_number_cell(cells, page_w, page_h)
        self.assertEqual(_normalize_drawing_number(sheet_cell.value_text), 'A-201')
        name_cell = _find_drawing_name_cell(cells, sheet_cell, page_w)
        self.assertEqual(name_cell.value_text, 'Exterior Elevations')

    def test_value_above_label_in_cell(self):
        lines = [
            TextLine(100, 120, 80, 200, 'A-212', [], 28, 22, 'right'),
            TextLine(130, 140, 80, 180, 'Drawing No.', [], 10, 7, 'right'),
        ]
        cell = _lines_to_labeled_cell(lines, med_h=12, med_size=10)
        self.assertEqual(cell.value_text, 'A-212')


if __name__ == '__main__':
    unittest.main()
