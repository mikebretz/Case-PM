/**
 * MS Project / Primavera P6 field catalog for schedule grid columns
 */
(function (global) {
    'use strict';

    const FIELDS = [
        { id: 'activity_id', label: 'Activity ID', map_to: 'activity_id', type: 'text', group: 'General', desc: 'Unique activity identifier (MS Project ID / P6 activity code)' },
        { id: 'text', label: 'Activity Name', map_to: 'text', type: 'text', group: 'General', desc: 'Task name / activity description', builtin: true },
        { id: 'wbs', label: 'WBS', map_to: 'wbs', type: 'readonly', group: 'General', desc: 'Work breakdown structure code', builtin: true },
        { id: 'duration', label: 'Duration', map_to: 'duration', type: 'number', group: 'Schedule', desc: 'Original duration in work days', builtin: true },
        { id: 'start_date', label: 'Start', map_to: 'start_date', type: 'date', group: 'Schedule', desc: 'Planned start date', builtin: true },
        { id: 'end_date', label: 'Finish', map_to: 'end_date', type: 'date', group: 'Schedule', desc: 'Planned finish date', builtin: true },
        { id: 'predecessors', label: 'Predecessors', map_to: 'predecessors', type: 'predecessor', group: 'Logic', desc: 'Driving logic (FS/SS/FF/SF + lag)', builtin: true },
        { id: 'successors', label: 'Successors', map_to: 'successors', type: 'successors', group: 'Logic', desc: 'Downstream relationships (read-only)' },
        { id: 'progress', label: '% Complete', map_to: 'progress', type: 'percent', group: 'Progress', desc: 'Physical percent complete', builtin: true },
        { id: 'actual_start', label: 'Actual Start', map_to: 'actual_start', type: 'date', group: 'Progress', desc: 'Actual start (as-built)' },
        { id: 'actual_finish', label: 'Actual Finish', map_to: 'actual_finish', type: 'date', group: 'Progress', desc: 'Actual finish (as-built)' },
        { id: 'remaining_duration', label: 'Remaining Duration', map_to: 'remaining_duration', type: 'number', group: 'Progress', desc: 'Days remaining to complete' },
        { id: 'resource', label: 'Resource Names', map_to: 'resource', type: 'text', group: 'Resources', desc: 'Assigned crews, trades, or equipment', builtin: true },
        { id: 'owner', label: 'Responsible Party', map_to: 'owner', type: 'text', group: 'Resources', desc: 'Subcontractor / responsible contact', builtin: true },
        { id: 'work_hours', label: 'Work (Hours)', map_to: 'work_hours', type: 'number', group: 'Resources', desc: 'Total work effort in hours' },
        { id: 'cost', label: 'Cost', map_to: 'cost', type: 'number', group: 'Cost', desc: 'Activity cost / budgeted cost' },
        { id: 'fixed_cost', label: 'Fixed Cost', map_to: 'fixed_cost', type: 'number', group: 'Cost', desc: 'Fixed cost amount' },
        { id: 'constraint_type', label: 'Constraint Type', map_to: 'constraint_type', type: 'select', group: 'Advanced', desc: 'ASAP, MSO, MFO, SNET, SNLT, FNET, FNLT' },
        { id: 'constraint_date', label: 'Constraint Date', map_to: 'constraint_date', type: 'date', group: 'Advanced', desc: 'Date for schedule constraint' },
        { id: 'deadline', label: 'Deadline', map_to: 'deadline', type: 'date', group: 'Advanced', desc: 'Must-finish-by deadline' },
        { id: 'priority', label: 'Priority', map_to: 'priority', type: 'select', group: 'Advanced', desc: '500=Highest, 1000=Normal (MS Project style)' },
        { id: 'calendar', label: 'Calendar', map_to: 'calendar', type: 'text', group: 'Advanced', desc: 'Calendar assigned to activity' },
        { id: 'activity_code', label: 'Activity Code', map_to: 'activity_code', type: 'text', group: 'Codes', desc: 'P6 activity code / custom code' },
        { id: 'phase', label: 'Phase', map_to: 'phase', type: 'text', group: 'Codes', desc: 'Construction phase grouping' },
        { id: 'discipline', label: 'Discipline', map_to: 'discipline', type: 'text', group: 'Codes', desc: 'Trade discipline (MEP, Structural, etc.)' },
        { id: 'bar_color', label: 'Bar Color', map_to: 'bar_color', type: 'color', group: 'Display', desc: 'Gantt bar color', builtin: true },
        { id: 'notes', label: 'Notes', map_to: 'notes', type: 'text', group: 'General', desc: 'Activity notes / remarks' },
        { id: 'hyperlink', label: 'Hyperlink', map_to: 'hyperlink', type: 'text', group: 'General', desc: 'Linked document URL' },
        { id: 'free_float', label: 'Free Float', map_to: 'free_float', type: 'readonly', group: 'CPM', desc: 'Free slack (days)' },
        { id: 'total_float', label: 'Total Float', map_to: 'total_float', type: 'readonly', group: 'CPM', desc: 'Total slack (days)' },
        { id: 'early_start', label: 'Early Start', map_to: 'early_start', type: 'readonly', group: 'CPM', desc: 'CPM early start' },
        { id: 'early_finish', label: 'Early Finish', map_to: 'early_finish', type: 'readonly', group: 'CPM', desc: 'CPM early finish' },
        { id: 'late_start', label: 'Late Start', map_to: 'late_start', type: 'readonly', group: 'CPM', desc: 'CPM late start' },
        { id: 'late_finish', label: 'Late Finish', map_to: 'late_finish', type: 'readonly', group: 'CPM', desc: 'CPM late finish' }
    ];

    function getField(id) {
        return FIELDS.find(f => f.id === id || f.map_to === id);
    }

    function getAddableFields(existingNames) {
        const exist = new Set(existingNames || []);
        return FIELDS.filter(f => !exist.has(f.map_to) && f.type !== 'readonly' && f.type !== 'successors');
    }

    function groupFields(fields) {
        const groups = {};
        fields.forEach(f => {
            if (!groups[f.group]) groups[f.group] = [];
            groups[f.group].push(f);
        });
        return groups;
    }

    global.CasePMScheduleFields = { FIELDS, getField, getAddableFields, groupFields };
})(typeof window !== 'undefined' ? window : global);
