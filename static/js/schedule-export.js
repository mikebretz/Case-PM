/**
 * Case PM — Export schedule to Primavera XER and MS Project XML
 */
(function (global) {
    'use strict';

    const GANTT_TO_P6 = { '0': 'PR_FS', '1': 'PR_SS', '2': 'PR_FF', '3': 'PR_SF' };
    const GANTT_TO_MS = { '0': '1', '1': '3', '2': '0', '3': '2' };

    function escTab(value) {
        return String(value == null ? '' : value).replace(/\t/g, ' ').replace(/\r?\n/g, ' ');
    }

    function p6Date(value) {
        if (!value) return '';
        const s = String(value).trim();
        if (s.length >= 10) return s.substring(0, 10) + ' 08:00';
        return '';
    }

    function durationHours(task) {
        const d = Number(task.duration) || 0;
        return Math.max(0, Math.round(d * 8));
    }

    function toXer(payload, meta) {
        const data = payload?.data || [];
        const links = payload?.links || [];
        const projectName = escTab(meta?.name || 'Case PM Schedule');
        let xer = '%E\n%V\t20\n';
        xer += '%T\tPROJECT\n%F\tproj_id\tproj_short_name\n';
        xer += `%R\t1\t${projectName}\n`;

        xer += '%T\tTASK\n%F\ttask_id\ttask_code\ttask_name\ttarget_start_date\ttarget_end_date\ttarget_drtn_hr_cnt\tphys_complete_pct\twbs_id\n';
        const idMap = new Map();
        let taskId = 1;
        data.forEach(t => {
            if (t.type === 'project') return;
            const tid = taskId++;
            idMap.set(String(t.id), tid);
            const code = escTab(t.activity_id || t.id);
            const name = escTab(t.text || code);
            const start = p6Date(t.start_date);
            const end = p6Date(t.end_date || t.start_date);
            const dur = durationHours(t);
            const pct = Math.round((Number(t.progress) || 0) * (Number(t.progress) > 1 ? 1 : 100));
            xer += `%R\t${tid}\t${code}\t${name}\t${start}\t${end}\t${dur}\t${pct}\t1\n`;
        });

        xer += '%T\tTASKPRED\n%F\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n';
        links.forEach(l => {
            const target = idMap.get(String(l.target));
            const source = idMap.get(String(l.source));
            if (!target || !source) return;
            const type = GANTT_TO_P6[String(l.type)] || 'PR_FS';
            const lag = Math.round((Number(l.lag) || 0) * 8);
            xer += `%R\t${target}\t${source}\t${type}\t${lag}\n`;
        });

        return xer;
    }

    function xmlEsc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function msDate(value) {
        if (!value) return '';
        const s = String(value).trim();
        return s.length >= 10 ? `${s.substring(0, 10)}T08:00:00` : '';
    }

    function toMsProjectXml(payload, meta) {
        const data = payload?.data || [];
        const links = payload?.links || [];
        const projectName = xmlEsc(meta?.name || 'Case PM Schedule');
        let xml = '<?xml version="1.0" encoding="UTF-8"?>\n';
        xml += '<Project xmlns="http://schemas.microsoft.com/project">\n';
        xml += `<Name>${projectName}</Name>\n`;
        xml += '<Tasks>\n';

        const uidMap = new Map();
        let uid = 1;
        data.forEach(t => {
            if (t.type === 'project') return;
            uidMap.set(String(t.id), uid);
            const milestone = t.type === 'milestone' ? 1 : 0;
            const pct = Math.round((Number(t.progress) || 0) * (Number(t.progress) > 1 ? 1 : 100));
            xml += '<Task>\n';
            xml += `<UID>${uid}</UID>\n`;
            xml += `<ID>${uid}</ID>\n`;
            xml += `<Name>${xmlEsc(t.text || `Task ${uid}`)}</Name>\n`;
            xml += `<Type>0</Type>\n`;
            xml += `<Milestone>${milestone}</Milestone>\n`;
            xml += `<Start>${msDate(t.start_date)}</Start>\n`;
            xml += `<Finish>${msDate(t.end_date || t.start_date)}</Finish>\n`;
            xml += `<Duration>PT${Math.max(0, Number(t.duration) || 0) * 8}H0M0S</Duration>\n`;
            xml += `<PercentComplete>${pct}</PercentComplete>\n`;
            xml += '</Task>\n';
            uid++;
        });
        xml += '</Tasks>\n';

        data.forEach(t => {
            if (t.type === 'project') return;
            const targetUid = uidMap.get(String(t.id));
            if (!targetUid) return;
            links.filter(l => String(l.target) === String(t.id)).forEach(l => {
                const sourceUid = uidMap.get(String(l.source));
                if (!sourceUid) return;
                xml += '<Task>\n';
                xml += `<UID>${targetUid}</UID>\n`;
                xml += '<PredecessorLink>\n';
                xml += `<PredecessorUID>${sourceUid}</PredecessorUID>\n`;
                xml += `<Type>${GANTT_TO_MS[String(l.type)] || '1'}</Type>\n`;
                xml += `<LinkLag>${(Number(l.lag) || 0) * 4800}</LinkLag>\n`;
                xml += '</PredecessorLink>\n';
                xml += '</Task>\n';
            });
        });

        xml += '</Project>\n';
        return xml;
    }

    global.CasePMScheduleExport = { toXer, toMsProjectXml };
})(typeof window !== 'undefined' ? window : global);
