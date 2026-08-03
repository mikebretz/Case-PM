#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DocumentStorageStemTests(unittest.TestCase):
    def test_strips_duplicate_extension(self):
        from document_features import document_storage_stem
        self.assertEqual(
            document_storage_stem('Sub_Change_Order.pdf', 'Sub_Change_Order.pdf', 'pdf'),
            'Sub_Change_Order',
        )

    def test_plain_name(self):
        from document_features import document_storage_stem
        self.assertEqual(document_storage_stem('Report', 'report.xlsx', 'xlsx'), 'Report')


if __name__ == '__main__':
    unittest.main()
