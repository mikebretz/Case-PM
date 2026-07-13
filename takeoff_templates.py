"""Takeoff finish templates — linear/area measurements expand to estimating line items."""
from __future__ import annotations

# factor applies to measured quantity (LF or SF depending on trigger)
TAKEOFF_FINISH_TEMPLATES = [
    {
        'id': 'int_wall_9',
        'label': 'Interior partition wall (9\' height)',
        'trigger': 'linear_ft',
        'description': 'Typical stud wall — drywall both sides, paint, base',
        'lines': [
            {'description': 'Metal studs & track', 'spec_section': '09 22 00', 'cost_code': '09 22 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
            {'description': 'Gypsum board (both sides)', 'spec_section': '09 21 00', 'cost_code': '09 21 00', 'unit': 'SF', 'factor': 18.0, 'cost_type': 'Subcontract'},
            {'description': 'Tape, finish & texture', 'spec_section': '09 29 00', 'cost_code': '09 29 00', 'unit': 'SF', 'factor': 18.0, 'cost_type': 'Subcontract'},
            {'description': 'Paint — walls', 'spec_section': '09 91 00', 'cost_code': '09 91 00', 'unit': 'SF', 'factor': 18.0, 'cost_type': 'Subcontract'},
            {'description': 'Base molding', 'spec_section': '06 20 00', 'cost_code': '06 20 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'int_wall_10',
        'label': 'Interior partition wall (10\' height)',
        'trigger': 'linear_ft',
        'description': 'Taller partition — drywall both sides, paint, base',
        'lines': [
            {'description': 'Metal studs & track', 'spec_section': '09 22 00', 'cost_code': '09 22 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
            {'description': 'Gypsum board (both sides)', 'spec_section': '09 21 00', 'cost_code': '09 21 00', 'unit': 'SF', 'factor': 20.0, 'cost_type': 'Subcontract'},
            {'description': 'Tape, finish & texture', 'spec_section': '09 29 00', 'cost_code': '09 29 00', 'unit': 'SF', 'factor': 20.0, 'cost_type': 'Subcontract'},
            {'description': 'Paint — walls', 'spec_section': '09 91 00', 'cost_code': '09 91 00', 'unit': 'SF', 'factor': 20.0, 'cost_type': 'Subcontract'},
            {'description': 'Base molding', 'spec_section': '06 20 00', 'cost_code': '06 20 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'furr_wall_8',
        'label': 'Furring / shaft wall (8\' height)',
        'trigger': 'linear_ft',
        'description': 'Single-side furring with gyp and paint',
        'lines': [
            {'description': 'Furring channels', 'spec_section': '09 22 00', 'cost_code': '09 22 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
            {'description': 'Gypsum board (one side)', 'spec_section': '09 21 00', 'cost_code': '09 21 00', 'unit': 'SF', 'factor': 8.0, 'cost_type': 'Subcontract'},
            {'description': 'Paint — walls', 'spec_section': '09 91 00', 'cost_code': '09 91 00', 'unit': 'SF', 'factor': 8.0, 'cost_type': 'Subcontract'},
        ],
    },
    {
        'id': 'base_only',
        'label': 'Base molding only',
        'trigger': 'linear_ft',
        'description': 'Wood or rubber base along measured run',
        'lines': [
            {'description': 'Base molding supply & install', 'spec_section': '06 20 00', 'cost_code': '06 20 00', 'unit': 'LF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'carpet_floor',
        'label': 'Carpet flooring',
        'trigger': 'area_sf',
        'description': 'Carpet tile or broadloom over measured area',
        'lines': [
            {'description': 'Carpet flooring', 'spec_section': '09 68 00', 'cost_code': '09 68 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Subcontract'},
            {'description': 'Carpet adhesive / prep', 'spec_section': '09 65 00', 'cost_code': '09 65 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'tile_floor',
        'label': 'Ceramic tile flooring',
        'trigger': 'area_sf',
        'description': 'Floor tile with setting materials',
        'lines': [
            {'description': 'Ceramic floor tile', 'spec_section': '09 30 00', 'cost_code': '09 30 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Subcontract'},
            {'description': 'Tile setting materials', 'spec_section': '09 30 00', 'cost_code': '09 30 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'paint_walls',
        'label': 'Paint walls (measured LF × 9\' height)',
        'trigger': 'linear_ft',
        'description': 'Paint only — assumes 9\' wall height',
        'lines': [
            {'description': 'Paint — walls', 'spec_section': '09 91 00', 'cost_code': '09 91 00', 'unit': 'SF', 'factor': 9.0, 'cost_type': 'Subcontract'},
        ],
    },
    {
        'id': 'concrete_slab',
        'label': 'Concrete slab on grade',
        'trigger': 'area_sf',
        'description': 'Place & finish slab over measured area',
        'lines': [
            {'description': 'Place & finish concrete slab', 'spec_section': '03 30 00', 'cost_code': '03 30 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Subcontract'},
            {'description': 'Vapor barrier', 'spec_section': '03 30 00', 'cost_code': '03 30 00', 'unit': 'SF', 'factor': 1.0, 'cost_type': 'Material'},
        ],
    },
    {
        'id': 'measure_only',
        'label': 'Raw measurement (no finish expansion)',
        'trigger': 'any',
        'description': 'Single line matching the drawn measurement',
        'lines': [],
    },
]


def list_finish_templates(trigger=None):
    rows = TAKEOFF_FINISH_TEMPLATES
    if trigger and trigger != 'any':
        rows = [t for t in rows if t['trigger'] in (trigger, 'any')]
    return rows


def expand_takeoff_template(template_id, quantity, unit='LF', markup_id=None, sheet_number=''):
    """Expand a finish template into worksheet-ready line dicts."""
    tpl = next((t for t in TAKEOFF_FINISH_TEMPLATES if t['id'] == template_id), None)
    if not tpl:
        return []
    qty = float(quantity or 0)
    if not qty:
        return []
    if not tpl['lines']:
        return [{
            'description': f'Takeoff — {sheet_number}' if sheet_number else 'Takeoff measurement',
            'quantity': qty,
            'unit': unit,
            'unit_cost': 0,
            'source': 'takeoff',
            'source_ref': f'takeoff:{markup_id}' if markup_id else 'takeoff',
            'markup_id': markup_id,
            'cost_code': '01-000',
            'spec_section': '',
            'cost_type': 'Subcontract',
        }]
    out = []
    for comp in tpl['lines']:
        line_qty = round(qty * float(comp.get('factor') or 1), 2)
        out.append({
            'description': comp['description'],
            'spec_section': comp.get('spec_section', ''),
            'cost_code': comp.get('cost_code', comp.get('spec_section', '01-000')),
            'quantity': line_qty,
            'unit': comp.get('unit', 'EA'),
            'unit_cost': 0,
            'cost_type': comp.get('cost_type', 'Subcontract'),
            'source': 'takeoff',
            'source_ref': f'takeoff:{markup_id}' if markup_id else f'takeoff:{template_id}',
            'markup_id': markup_id,
            'group_key': f'takeoff-{template_id}',
            'meta': {'template_id': template_id, 'template_label': tpl['label']},
        })
    return out
