"""Unit tests for cost_code_library."""
from cost_code_library import (
    library_slice_from_state,
    merge_library_patch,
    picker_cost_codes,
)


def test_picker_merges_budget_and_custom():
    state = {
        'budgetLines': [
            {'cost_code': '01-100', 'description': 'General', 'cost_type': 'Labor'},
        ],
        'customCostCodes': [
            {'code': '99-999', 'description': 'Misc', 'cost_type': 'Other'},
            {'code': '01-100', 'description': 'Dup', 'cost_type': 'X'},
        ],
    }
    codes = picker_cost_codes(state)
    assert len(codes) == 2
    assert codes[0]['code'] == '01-100'
    assert codes[0]['source'] == 'budget'
    assert codes[1]['code'] == '99-999'
    assert codes[1]['source'] == 'library'


def test_merge_library_patch_preserves_budget_lines():
    existing = {'budgetLines': [{'cost_code': 'A'}], 'costTypes': ['Labor']}
    merged = merge_library_patch(existing, {'costTypes': ['Labor', 'Material'], 'customCostCodes': [{'code': 'B'}]})
    assert merged['budgetLines'] == [{'cost_code': 'A'}]
    assert merged['costTypes'] == ['Labor', 'Material']
    assert merged['customCostCodes'] == [{'code': 'B'}]


def test_library_slice():
    sl = library_slice_from_state({'costTypes': ['A'], 'activeCostCodeList': 'custom', 'budgetLines': []})
    assert sl['activeCostCodeList'] == 'custom'
    assert sl['costTypes'] == ['A']


def test_csi_active_list_migrates_to_custom():
    from cost_code_library import _normalize_active_list, library_slice_from_state

    assert _normalize_active_list('csi') == 'custom'
    assert _normalize_active_list(None) == 'custom'
    sl = library_slice_from_state({'activeCostCodeList': 'csi'})
    assert sl['activeCostCodeList'] == 'custom'


if __name__ == '__main__':
    test_picker_merges_budget_and_custom()
    test_merge_library_patch_preserves_budget_lines()
    test_library_slice()
    test_csi_active_list_migrates_to_custom()
    print('all ok')
