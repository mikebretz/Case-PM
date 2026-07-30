"""Payroll employees, deductions, pay runs, and calculations."""
from __future__ import annotations

import json
from datetime import date

FICA_EMPLOYEE_RATE = 0.062
MEDICARE_EMPLOYEE_RATE = 0.0145
FICA_EMPLOYER_RATE = 0.062
MEDICARE_EMPLOYER_RATE = 0.0145
OT_MULTIPLIER = 1.5


def _periods_per_year(freq: str) -> int:
    return {'weekly': 52, 'biweekly': 26, 'semimonthly': 24, 'monthly': 12}.get(freq or 'biweekly', 26)


def serialize_employee(e):
    return {
        'id': e.id,
        'employee_number': e.employee_number,
        'first_name': e.first_name,
        'last_name': e.last_name,
        'name': f'{e.first_name} {e.last_name}'.strip(),
        'status': e.status,
        'pay_type': e.pay_type or 'hourly',
        'hourly_rate': float(e.hourly_rate or 0),
        'annual_salary': float(e.annual_salary or 0),
        'default_project_id': e.default_project_id,
        'department': e.department or '',
        'user_id': e.user_id,
        'federal_wh_percent': float(e.federal_wh_percent or 0),
        'state_wh_percent': float(e.state_wh_percent or 0),
        'payment_method': e.payment_method or 'direct_deposit',
        'bank_account_last4': e.bank_account_last4 or '',
    }


def serialize_deduction(d):
    return {
        'id': d.id,
        'code': d.code,
        'description': d.description or '',
        'deduction_type': d.deduction_type or 'posttax',
        'calc_method': d.calc_method or 'fixed',
        'amount': float(d.amount or 0),
        'percent': float(d.percent or 0),
        'is_active': bool(d.is_active),
    }


def serialize_run(r, lines=None):
    return {
        'id': r.id,
        'run_number': r.run_number,
        'pay_date': r.pay_date.isoformat() if r.pay_date else None,
        'period_start': r.period_start.isoformat() if getattr(r, 'period_start', None) else None,
        'period_end': r.period_end.isoformat() if getattr(r, 'period_end', None) else None,
        'pay_frequency': getattr(r, 'pay_frequency', None) or 'biweekly',
        'status': r.status,
        'total_gross': float(r.total_gross or 0),
        'total_net': float(r.total_net or 0),
        'total_taxes': float(getattr(r, 'total_taxes', 0) or 0),
        'total_deductions': float(getattr(r, 'total_deductions', 0) or 0),
        'total_employer_taxes': float(getattr(r, 'total_employer_taxes', 0) or 0),
        'journal_batch_id': r.journal_batch_id,
        'notes': getattr(r, 'notes', None) or '',
        'lines': lines or [],
    }


def serialize_run_line(ln, employee=None):
    emp = employee or getattr(ln, 'employee', None)
    name = ''
    if emp:
        name = f'{emp.first_name} {emp.last_name}'
    return {
        'id': ln.id,
        'run_id': ln.run_id,
        'employee_id': ln.employee_id,
        'employee_name': name,
        'hours_regular': float(ln.hours_regular or 0),
        'hours_overtime': float(ln.hours_overtime or 0),
        'gross_pay': float(ln.gross_pay or 0),
        'federal_wh': float(ln.federal_wh or 0),
        'state_wh': float(ln.state_wh or 0),
        'fica_employee': float(ln.fica_employee or 0),
        'medicare_employee': float(ln.medicare_employee or 0),
        'other_deductions': float(ln.other_deductions or 0),
        'net_pay': float(ln.net_pay or 0),
        'employer_fica': float(ln.employer_fica or 0),
        'employer_medicare': float(ln.employer_medicare or 0),
        'project_id': ln.project_id,
        'check_number': ln.check_number,
        'payment_method': ln.payment_method,
    }


def _employee_deduction_total(db, models, employee_id, gross):
    AcctPayrollEmployeeDeduction = models['AcctPayrollEmployeeDeduction']
    AcctPayrollDeduction = models['AcctPayrollDeduction']
    total = 0.0
    rows = AcctPayrollEmployeeDeduction.query.filter_by(employee_id=employee_id).all()
    for row in rows:
        d = AcctPayrollDeduction.query.get(row.deduction_id)
        if not d or not d.is_active:
            continue
        if row.override_amount is not None:
            total += float(row.override_amount)
        elif (d.calc_method or 'fixed') == 'percent':
            total += round(gross * float(d.percent or 0) / 100.0, 2)
        else:
            total += float(d.amount or 0)
    return round(total, 2)


def calculate_pay_line(db, models, employee, *, hours_regular=0, hours_overtime=0, gross_override=None, pay_frequency='biweekly'):
    """Compute gross, withholdings, and net for one employee."""
    if gross_override is not None:
        gross = round(float(gross_override), 2)
    elif (employee.pay_type or 'hourly') == 'salary':
        gross = round(float(employee.annual_salary or 0) / _periods_per_year(pay_frequency), 2)
    else:
        rate = float(employee.hourly_rate or 0)
        gross = round(
            float(hours_regular or 0) * rate + float(hours_overtime or 0) * rate * OT_MULTIPLIER,
            2,
        )

    federal = round(gross * float(employee.federal_wh_percent or 0) / 100.0, 2)
    state = round(gross * float(employee.state_wh_percent or 0) / 100.0, 2)
    fica = round(gross * FICA_EMPLOYEE_RATE, 2)
    medicare = round(gross * MEDICARE_EMPLOYEE_RATE, 2)
    deductions = _employee_deduction_total(db, models, employee.id, gross)
    taxes = round(federal + state + fica + medicare, 2)
    net = round(gross - taxes - deductions, 2)
    employer_fica = round(gross * FICA_EMPLOYER_RATE, 2)
    employer_medicare = round(gross * MEDICARE_EMPLOYER_RATE, 2)

    return {
        'gross_pay': gross,
        'federal_wh': federal,
        'state_wh': state,
        'fica_employee': fica,
        'medicare_employee': medicare,
        'other_deductions': deductions,
        'net_pay': max(net, 0),
        'employer_fica': employer_fica,
        'employer_medicare': employer_medicare,
        'employee_taxes': taxes,
        'employer_taxes': round(employer_fica + employer_medicare, 2),
    }


def recalculate_run(db, models, run_id):
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    run = AcctPayrollRun.query.get(int(run_id))
    if not run:
        raise ValueError('Payroll run not found')
    lines = AcctPayrollRunLine.query.filter_by(run_id=run.id).all()
    tg = tn = tt = td = te = 0.0
    for ln in lines:
        emp = AcctPayrollEmployee.query.get(ln.employee_id)
        if not emp:
            continue
        freq = getattr(run, 'pay_frequency', None) or 'biweekly'
        if (emp.pay_type or 'hourly') == 'salary':
            calc = calculate_pay_line(db, models, emp, pay_frequency=freq)
        else:
            calc = calculate_pay_line(
                db, models, emp,
                hours_regular=ln.hours_regular,
                hours_overtime=ln.hours_overtime,
                pay_frequency=freq,
            )
        ln.gross_pay = calc['gross_pay']
        ln.federal_wh = calc['federal_wh']
        ln.state_wh = calc['state_wh']
        ln.fica_employee = calc['fica_employee']
        ln.medicare_employee = calc['medicare_employee']
        ln.other_deductions = calc['other_deductions']
        ln.net_pay = calc['net_pay']
        ln.employer_fica = calc['employer_fica']
        ln.employer_medicare = calc['employer_medicare']
        if not ln.project_id:
            ln.project_id = emp.default_project_id
        if not ln.payment_method:
            ln.payment_method = emp.payment_method
        tg += calc['gross_pay']
        tn += calc['net_pay']
        tt += calc['employee_taxes']
        td += calc['other_deductions']
        te += calc['employer_taxes']
    run.total_gross = round(tg, 2)
    run.total_net = round(tn, 2)
    run.total_taxes = round(tt, 2)
    run.total_deductions = round(td, 2)
    run.total_employer_taxes = round(te, 2)
    db.session.flush()
    return serialize_run(run, [serialize_run_line(ln, AcctPayrollEmployee.query.get(ln.employee_id)) for ln in lines])


def build_run_from_employees(db, models, ledger_id, run_id, *, default_hours=40.0):
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    run = AcctPayrollRun.query.get(int(run_id))
    if not run or run.ledger_id != ledger_id:
        raise ValueError('Payroll run not found')
    if run.status != 'Open':
        raise ValueError('Cannot modify a posted payroll run')
    existing = {ln.employee_id for ln in AcctPayrollRunLine.query.filter_by(run_id=run.id).all()}
    employees = AcctPayrollEmployee.query.filter_by(ledger_id=ledger_id, status='Active').all()
    added = 0
    for emp in employees:
        if emp.id in existing:
            continue
        hrs_reg = default_hours if (emp.pay_type or 'hourly') == 'hourly' else 0
        ln = AcctPayrollRunLine(
            run_id=run.id,
            employee_id=emp.id,
            hours_regular=hrs_reg,
            hours_overtime=0,
            project_id=emp.default_project_id,
            payment_method=emp.payment_method,
        )
        db.session.add(ln)
        added += 1
    db.session.flush()
    return {'added': added, 'run': recalculate_run(db, models, run.id)}


def payroll_register(db, models, ledger_id, limit=100):
    AcctPayrollRun = models['AcctPayrollRun']
    AcctPayrollRunLine = models['AcctPayrollRunLine']
    AcctPayrollEmployee = models['AcctPayrollEmployee']
    runs = AcctPayrollRun.query.filter_by(ledger_id=ledger_id).order_by(AcctPayrollRun.id.desc()).limit(limit).all()
    out = []
    for run in runs:
        lines = AcctPayrollRunLine.query.filter_by(run_id=run.id).all()
        out.append(serialize_run(run, [
            serialize_run_line(ln, AcctPayrollEmployee.query.get(ln.employee_id)) for ln in lines
        ]))
    return {'runs': out}
