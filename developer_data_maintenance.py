"""Developer maintenance — clear module data by project scope."""
from __future__ import annotations

import os
import shutil
from typing import Any

MODULE_CATALOG: list[dict[str, Any]] = [
    {'key': 'documents', 'label': 'Documents', 'description': 'Files, folders, versions, markups, and share links', 'icon': 'fa-folder-open', 'color': 'text-violet-400', 'scope': 'project'},
    {'key': 'drawings', 'label': 'Drawings', 'description': 'Sheets, revisions, markups, and drawing uploads', 'icon': 'fa-drafting-compass', 'color': 'text-cyan-400', 'scope': 'project'},
    {'key': 'rfis', 'label': 'RFIs', 'description': 'RFI log and attachment folders', 'icon': 'fa-circle-question', 'color': 'text-blue-400', 'scope': 'project'},
    {'key': 'change_orders', 'label': 'Change Orders', 'description': 'Change orders, PCOs, change events, RFQs, CORs, allocations, and attachments', 'icon': 'fa-file-contract', 'color': 'text-emerald-400', 'scope': 'project'},
    {'key': 'commitments', 'label': 'Commitments', 'description': 'Subcontracts, POs, allocations, and files', 'icon': 'fa-handshake', 'color': 'text-orange-400', 'scope': 'project'},
    {'key': 'budget', 'label': 'Budget', 'description': 'Budget worksheet state per project', 'icon': 'fa-chart-pie', 'color': 'text-teal-400', 'scope': 'project'},
    {'key': 'pay_apps', 'label': 'Pay Applications', 'description': 'G702/G703 and subcontractor pay app state', 'icon': 'fa-file-invoice-dollar', 'color': 'text-amber-400', 'scope': 'project'},
    {'key': 'submittals', 'label': 'Submittals', 'description': 'Submittal log and attachment folders', 'icon': 'fa-clipboard-check', 'color': 'text-pink-400', 'scope': 'project'},
    {'key': 'punch_list', 'label': 'Punch List', 'description': 'Punch items and photo attachments', 'icon': 'fa-list-check', 'color': 'text-rose-400', 'scope': 'project'},
    {'key': 'daily_log', 'label': 'Daily Log', 'description': 'Daily logs, manpower, equipment, and attachments', 'icon': 'fa-calendar-day', 'color': 'text-sky-400', 'scope': 'project'},
    {'key': 'weekly_report', 'label': 'Weekly Report', 'description': 'Weekly and biweekly report records', 'icon': 'fa-calendar-week', 'color': 'text-indigo-400', 'scope': 'project'},
    {'key': 'safety', 'label': 'Safety', 'description': 'Incidents, certifications, training, and files', 'icon': 'fa-hard-hat', 'color': 'text-yellow-400', 'scope': 'project'},
    {'key': 'schedule', 'label': 'Schedule', 'description': 'CPM schedule payload and legacy task rows', 'icon': 'fa-calendar-days', 'color': 'text-lime-400', 'scope': 'project'},
    {'key': 'deliveries', 'label': 'Deliveries', 'description': 'Scheduled delivery records', 'icon': 'fa-truck', 'color': 'text-fuchsia-400', 'scope': 'project'},
    {'key': 'inspections', 'label': 'Permits & Inspections', 'description': 'Permit and inspection tracking', 'icon': 'fa-clipboard-list', 'color': 'text-orange-300', 'scope': 'project'},
    {'key': 'meeting_minutes', 'label': 'Meeting Minutes', 'description': 'Meetings, action items, and recordings', 'icon': 'fa-users-rectangle', 'color': 'text-purple-400', 'scope': 'project'},
    {'key': 'photos', 'label': 'Photos', 'description': 'Project photo gallery files', 'icon': 'fa-camera', 'color': 'text-zinc-300', 'scope': 'project'},
    {'key': 'project_assets', 'label': 'Project Assets', 'description': 'Logos, spec books, and original contract PDFs', 'icon': 'fa-building', 'color': 'text-sky-300', 'scope': 'project'},
    {'key': 'sage_sync', 'label': 'Sage Sync Events', 'description': 'Sage integration event queue/history', 'icon': 'fa-arrows-rotate', 'color': 'text-emerald-300', 'scope': 'project'},
    {'key': 'projects', 'label': 'Projects (full delete)', 'description': 'Delete project records and ALL related module data', 'icon': 'fa-building-circle-xmark', 'color': 'text-red-400', 'scope': 'project', 'danger': True},
    {'key': 'companies', 'label': 'Companies & COI', 'description': 'Company directory and certificate files (program-wide)', 'icon': 'fa-industry', 'color': 'text-zinc-400', 'scope': 'global'},
    {'key': 'audit_log', 'label': 'Audit Log', 'description': 'Audit history for selected projects or entire program', 'icon': 'fa-list-check', 'color': 'text-zinc-500', 'scope': 'mixed'},
]

_PROJECT_MODULE_KEYS = tuple(m['key'] for m in MODULE_CATALOG if m.get('scope') == 'project' and m['key'] != 'projects')


def maintenance_catalog_for_api(Project):
  """Return module list and projects for the developer maintenance UI."""
  projects = Project.query.order_by(Project.number, Project.name).all()
  return {
    'modules': MODULE_CATALOG,
    'projects': [
      {
        'id': p.id,
        'number': p.number or '',
        'name': p.name or '',
        'status': p.status or '',
        'label': f'{p.number or p.id} — {p.name}'.strip(' —'),
      }
      for p in projects
    ],
  }


def resolve_project_ids(db, Project, *, all_projects: bool, project_ids: list[int] | None):
  """Validate and resolve target project ids."""
  if all_projects:
    ids = [p.id for p in Project.query.with_entities(Project.id).all()]
    return ids, None
  raw = []
  for value in project_ids or []:
    try:
      raw.append(int(value))
    except (TypeError, ValueError):
      continue
  raw = sorted(set(raw))
  if not raw:
    return [], 'Select at least one project, or choose All Projects.'
  existing = {p.id for p in Project.query.filter(Project.id.in_(raw)).with_entities(Project.id).all()}
  missing = [pid for pid in raw if pid not in existing]
  if missing:
    return [], f'Unknown project id(s): {", ".join(str(m) for m in missing)}'
  return raw, None


def _safe_rmtree(path: str):
  if path and os.path.isdir(path):
    shutil.rmtree(path, ignore_errors=True)


def _clear_documents(db, project_ids, models, upload_root):
  Document = models['Document']
  DocumentFolder = models['DocumentFolder']
  DocumentShareLink = models['DocumentShareLink']
  DocumentFolderShareLink = models['DocumentFolderShareLink']
  DocumentVersion = models['DocumentVersion']
  DocumentComment = models['DocumentComment']
  DocumentActivity = models['DocumentActivity']
  DocumentMarkup = models['DocumentMarkup']
  DocumentFolderPermission = models['DocumentFolderPermission']
  MeetingMinute = models.get('MeetingMinute')
  Photo = models.get('Photo')

  doc_ids = [r.id for r in Document.query.filter(Document.project_id.in_(project_ids)).with_entities(Document.id).all()]
  folder_ids = [r.id for r in DocumentFolder.query.filter(DocumentFolder.project_id.in_(project_ids)).with_entities(DocumentFolder.id).all()]

  if MeetingMinute is not None and doc_ids:
    MeetingMinute.query.filter(MeetingMinute.document_id.in_(doc_ids)).update(
      {MeetingMinute.document_id: None}, synchronize_session=False
    )
  if Photo is not None and doc_ids:
    Photo.query.filter(Photo.document_id.in_(doc_ids)).update({Photo.document_id: None}, synchronize_session=False)

  if doc_ids:
    DocumentMarkup.query.filter(DocumentMarkup.document_id.in_(doc_ids)).delete(synchronize_session=False)
    DocumentComment.query.filter(DocumentComment.document_id.in_(doc_ids)).delete(synchronize_session=False)
    DocumentVersion.query.filter(DocumentVersion.document_id.in_(doc_ids)).delete(synchronize_session=False)
    DocumentShareLink.query.filter(DocumentShareLink.document_id.in_(doc_ids)).delete(synchronize_session=False)
    Document.query.filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)

  if folder_ids:
    DocumentFolderPermission.query.filter(DocumentFolderPermission.folder_id.in_(folder_ids)).delete(synchronize_session=False)
    DocumentFolderShareLink.query.filter(DocumentFolderShareLink.folder_id.in_(folder_ids)).delete(synchronize_session=False)
    DocumentFolder.query.filter(DocumentFolder.id.in_(folder_ids)).delete(synchronize_session=False)

  DocumentActivity.query.filter(DocumentActivity.project_id.in_(project_ids)).delete(synchronize_session=False)

  for pid in project_ids:
    ver_root = os.path.join(upload_root, 'documents', str(pid), 'versions')
    if os.path.isdir(ver_root):
      _safe_rmtree(ver_root)
    _safe_rmtree(os.path.join(upload_root, 'documents', str(pid)))

  return {'documents_deleted': len(doc_ids), 'folders_deleted': len(folder_ids)}


def _clear_drawings(db, project_ids, models, upload_root):
  from drawing_persistence import delete_drawing_record
  Drawing = models['Drawing']
  DrawingRevision = models['DrawingRevision']
  DrawingMarkup = models['DrawingMarkup']
  RFI = models.get('RFI')
  ChangeOrder = models.get('ChangeOrder')
  PunchItem = models.get('PunchItem')

  deleted = 0
  for pid in project_ids:
    drawings = Drawing.query.filter_by(project_id=pid).all()
    for drawing in drawings:
      delete_drawing_record(
        db, Drawing, DrawingRevision, DrawingMarkup, drawing, upload_root=upload_root,
        RFI=RFI, ChangeOrder=ChangeOrder, PunchItem=PunchItem,
      )
      deleted += 1
    _safe_rmtree(os.path.join(upload_root, 'drawings', str(pid)))
  return {'drawings_deleted': deleted}


def _clear_rfis(db, project_ids, models, upload_root):
  RFI = models['RFI']
  DrawingMarkup = models.get('DrawingMarkup')
  ChangeOrder = models.get('ChangeOrder')
  PotentialChangeOrder = models.get('PotentialChangeOrder')

  rfi_ids = [r.id for r in RFI.query.filter(RFI.project_id.in_(project_ids)).with_entities(RFI.id).all()]
  if rfi_ids:
    if DrawingMarkup is not None:
      DrawingMarkup.query.filter(DrawingMarkup.linked_rfi_id.in_(rfi_ids)).update(
        {DrawingMarkup.linked_rfi_id: None}, synchronize_session=False
      )
    if ChangeOrder is not None:
      ChangeOrder.query.filter(ChangeOrder.linked_rfi_id.in_(rfi_ids)).update(
        {ChangeOrder.linked_rfi_id: None}, synchronize_session=False
      )
    if PotentialChangeOrder is not None:
      PotentialChangeOrder.query.filter(PotentialChangeOrder.linked_rfi_id.in_(rfi_ids)).update(
        {PotentialChangeOrder.linked_rfi_id: None}, synchronize_session=False
      )
    for rid in rfi_ids:
      _safe_rmtree(os.path.join(upload_root, 'rfis', str(rid)))
    RFI.query.filter(RFI.id.in_(rfi_ids)).delete(synchronize_session=False)
  return {'rfis_deleted': len(rfi_ids)}


def _clear_change_orders(db, project_ids, models, upload_root):
  ChangeOrder = models['ChangeOrder']
  ChangeOrderAllocation = models['ChangeOrderAllocation']
  ChangeOrderRevision = models['ChangeOrderRevision']
  PotentialChangeOrder = models['PotentialChangeOrder']
  PCOAllocation = models['PCOAllocation']
  ChangeEvent = models.get('ChangeEvent')
  SubcontractorRFQ = models.get('SubcontractorRFQ')
  RFQAllocation = models.get('RFQAllocation')
  ChangeOrderRequest = models.get('ChangeOrderRequest')
  CORAllocation = models.get('CORAllocation')

  co_ids = [r.id for r in ChangeOrder.query.filter(ChangeOrder.project_id.in_(project_ids)).with_entities(ChangeOrder.id).all()]
  pco_ids = [r.id for r in PotentialChangeOrder.query.filter(PotentialChangeOrder.project_id.in_(project_ids)).with_entities(PotentialChangeOrder.id).all()]

  stats = {'change_orders_deleted': 0, 'pcos_deleted': 0, 'change_events_deleted': 0}

  if pco_ids:
    PotentialChangeOrder.query.filter(PotentialChangeOrder.id.in_(pco_ids)).update(
      {PotentialChangeOrder.change_order_id: None}, synchronize_session=False
    )

  if co_ids:
    ChangeOrder.query.filter(ChangeOrder.id.in_(co_ids)).update(
      {ChangeOrder.linked_owner_co_id: None}, synchronize_session=False
    )
    ChangeOrderAllocation.query.filter(ChangeOrderAllocation.change_order_id.in_(co_ids)).delete(synchronize_session=False)
    ChangeOrderRevision.query.filter(ChangeOrderRevision.change_order_id.in_(co_ids)).delete(synchronize_session=False)
    for cid in co_ids:
      _safe_rmtree(os.path.join(upload_root, 'change_orders', str(cid)))
    stats['change_orders_deleted'] = ChangeOrder.query.filter(ChangeOrder.id.in_(co_ids)).delete(synchronize_session=False)

  if pco_ids:
    PCOAllocation.query.filter(PCOAllocation.pco_id.in_(pco_ids)).delete(synchronize_session=False)
    for pid in pco_ids:
      _safe_rmtree(os.path.join(upload_root, 'change_orders', f'pco_{pid}'))
    stats['pcos_deleted'] = PotentialChangeOrder.query.filter(PotentialChangeOrder.id.in_(pco_ids)).delete(synchronize_session=False)

  if ChangeEvent is not None:
    ce_ids = [r.id for r in ChangeEvent.query.filter(ChangeEvent.project_id.in_(project_ids)).with_entities(ChangeEvent.id).all()]
    if ce_ids:
      if ChangeOrderRequest is not None and CORAllocation is not None:
        cor_ids = [r.id for r in ChangeOrderRequest.query.filter(ChangeOrderRequest.change_event_id.in_(ce_ids)).with_entities(ChangeOrderRequest.id).all()]
        if cor_ids:
          CORAllocation.query.filter(CORAllocation.cor_id.in_(cor_ids)).delete(synchronize_session=False)
        ChangeOrderRequest.query.filter(ChangeOrderRequest.change_event_id.in_(ce_ids)).delete(synchronize_session=False)
      if SubcontractorRFQ is not None and RFQAllocation is not None:
        rfq_ids = [r.id for r in SubcontractorRFQ.query.filter(SubcontractorRFQ.change_event_id.in_(ce_ids)).with_entities(SubcontractorRFQ.id).all()]
        if rfq_ids:
          RFQAllocation.query.filter(RFQAllocation.rfq_id.in_(rfq_ids)).delete(synchronize_session=False)
        SubcontractorRFQ.query.filter(SubcontractorRFQ.change_event_id.in_(ce_ids)).delete(synchronize_session=False)
      stats['change_events_deleted'] = ChangeEvent.query.filter(ChangeEvent.id.in_(ce_ids)).delete(synchronize_session=False)

  return stats


def _clear_commitments(db, project_ids, models, upload_root):
  Commitment = models['Commitment']
  CommitmentAllocation = models['CommitmentAllocation']
  c_ids = [r.id for r in Commitment.query.filter(Commitment.project_id.in_(project_ids)).with_entities(Commitment.id).all()]
  if c_ids:
    CommitmentAllocation.query.filter(CommitmentAllocation.commitment_id.in_(c_ids)).delete(synchronize_session=False)
    for cid in c_ids:
      _safe_rmtree(os.path.join(upload_root, 'commitments', str(cid)))
    Commitment.query.filter(Commitment.id.in_(c_ids)).delete(synchronize_session=False)
  return {'commitments_deleted': len(c_ids)}


def _clear_budget(db, project_ids, models, _upload_root):
  BudgetProjectState = models['BudgetProjectState']
  count = BudgetProjectState.query.filter(BudgetProjectState.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'budget_states_deleted': count}


def _clear_pay_apps(db, project_ids, models, _upload_root):
  PayAppProjectState = models['PayAppProjectState']
  count = PayAppProjectState.query.filter(PayAppProjectState.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'pay_app_states_deleted': count}


def _clear_submittals(db, project_ids, models, upload_root):
  Submittal = models['Submittal']
  s_ids = [r.id for r in Submittal.query.filter(Submittal.project_id.in_(project_ids)).with_entities(Submittal.id).all()]
  for sid in s_ids:
    _safe_rmtree(os.path.join(upload_root, 'submittals', str(sid)))
  if s_ids:
    Submittal.query.filter(Submittal.id.in_(s_ids)).delete(synchronize_session=False)
  return {'submittals_deleted': len(s_ids)}


def _clear_punch_list(db, project_ids, models, upload_root):
  PunchItem = models['PunchItem']
  item_ids = [r.id for r in PunchItem.query.filter(PunchItem.project_id.in_(project_ids)).with_entities(PunchItem.id).all()]
  for iid in item_ids:
    _safe_rmtree(os.path.join(upload_root, 'punch', str(iid)))
  if item_ids:
    PunchItem.query.filter(PunchItem.id.in_(item_ids)).delete(synchronize_session=False)
  return {'punch_items_deleted': len(item_ids)}


def _clear_daily_log(db, project_ids, models, upload_root):
  DailyLog = models['DailyLog']
  ManpowerEntry = models['ManpowerEntry']
  EquipmentEntry = models['EquipmentEntry']
  log_ids = [r.id for r in DailyLog.query.filter(DailyLog.project_id.in_(project_ids)).with_entities(DailyLog.id).all()]
  if log_ids:
    ManpowerEntry.query.filter(ManpowerEntry.daily_log_id.in_(log_ids)).delete(synchronize_session=False)
    EquipmentEntry.query.filter(EquipmentEntry.daily_log_id.in_(log_ids)).delete(synchronize_session=False)
    for lid in log_ids:
      _safe_rmtree(os.path.join(upload_root, 'daily_logs', str(lid)))
    DailyLog.query.filter(DailyLog.id.in_(log_ids)).delete(synchronize_session=False)
  return {'daily_logs_deleted': len(log_ids)}


def _clear_weekly_report(db, project_ids, models, _upload_root):
  WeeklyReport = models['WeeklyReport']
  count = WeeklyReport.query.filter(WeeklyReport.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'weekly_reports_deleted': count}


def _clear_safety(db, project_ids, models, upload_root):
  SafetyReport = models['SafetyReport']
  SafetyCertification = models['SafetyCertification']
  SafetyTrainingEvent = models['SafetyTrainingEvent']

  report_ids = [r.id for r in SafetyReport.query.filter(SafetyReport.project_id.in_(project_ids)).with_entities(SafetyReport.id).all()]
  for rid in report_ids:
    _safe_rmtree(os.path.join(upload_root, 'safety', str(rid)))
  reports_deleted = 0
  if report_ids:
    reports_deleted = SafetyReport.query.filter(SafetyReport.id.in_(report_ids)).delete(synchronize_session=False)

  certs_deleted = SafetyCertification.query.filter(SafetyCertification.project_id.in_(project_ids)).delete(synchronize_session=False)
  training_deleted = SafetyTrainingEvent.query.filter(SafetyTrainingEvent.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {
    'safety_reports_deleted': reports_deleted,
    'certifications_deleted': certs_deleted,
    'training_events_deleted': training_deleted,
  }


def _clear_schedule(db, project_ids, models, _upload_root):
  ScheduleData = models['ScheduleData']
  ScheduleTask = models['ScheduleTask']
  data_deleted = ScheduleData.query.filter(ScheduleData.project_id.in_(project_ids)).delete(synchronize_session=False)
  tasks_deleted = ScheduleTask.query.filter(ScheduleTask.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'schedule_data_deleted': data_deleted, 'schedule_tasks_deleted': tasks_deleted}


def _clear_deliveries(db, project_ids, models, _upload_root):
  Delivery = models['Delivery']
  count = Delivery.query.filter(Delivery.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'deliveries_deleted': count}


def _clear_inspections(db, project_ids, models, _upload_root):
  PermitInspectionItem = models['PermitInspectionItem']
  PermitInspectionItem.query.filter(PermitInspectionItem.project_id.in_(project_ids)).update(
    {PermitInspectionItem.parent_id: None}, synchronize_session=False
  )
  count = PermitInspectionItem.query.filter(PermitInspectionItem.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'inspections_deleted': count}


def _clear_meeting_minutes(db, project_ids, models, upload_root):
  MeetingMinute = models['MeetingMinute']
  MeetingActionItem = models['MeetingActionItem']
  meeting_ids = [r.id for r in MeetingMinute.query.filter(MeetingMinute.project_id.in_(project_ids)).with_entities(MeetingMinute.id).all()]
  if meeting_ids:
    MeetingActionItem.query.filter(MeetingActionItem.meeting_id.in_(meeting_ids)).delete(synchronize_session=False)
    MeetingActionItem.query.filter(MeetingActionItem.project_id.in_(project_ids)).delete(synchronize_session=False)
    for mid in meeting_ids:
      for pid in project_ids:
        _safe_rmtree(os.path.join(upload_root, 'meetings', str(pid), str(mid)))
    MeetingMinute.query.filter(MeetingMinute.id.in_(meeting_ids)).delete(synchronize_session=False)
  return {'meetings_deleted': len(meeting_ids)}


def _clear_photos(db, project_ids, models, upload_root):
  Photo = models['Photo']
  count = Photo.query.filter(Photo.project_id.in_(project_ids)).delete(synchronize_session=False)
  for pid in project_ids:
    _safe_rmtree(os.path.join(upload_root, 'photos', str(pid)))
  return {'photos_deleted': count}


def _clear_project_assets(db, _db, project_ids, _models, upload_root):
  for pid in project_ids:
    _safe_rmtree(os.path.join(upload_root, 'contracts', str(pid)))
    _safe_rmtree(os.path.join(upload_root, 'spec_books', str(pid)))
    _safe_rmtree(os.path.join(upload_root, 'projects', str(pid)))
  return {'project_asset_folders_cleared': len(project_ids)}


def _clear_sage_sync(db, project_ids, models, _upload_root):
  SageSyncEvent = models['SageSyncEvent']
  count = SageSyncEvent.query.filter(SageSyncEvent.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'sage_events_deleted': count}


def _clear_companies(db, _project_ids, models, upload_root):
  Company = models['Company']
  COI = models['COI']
  COI.query.delete(synchronize_session=False)
  count = Company.query.delete(synchronize_session=False)
  _safe_rmtree(os.path.join(upload_root, 'coi'))
  os.makedirs(os.path.join(upload_root, 'coi'), exist_ok=True)
  return {'companies_deleted': count}


def _clear_audit_log(db, project_ids, models, _upload_root, *, all_projects: bool):
  AuditLog = models['AuditLog']
  if all_projects:
    count = AuditLog.query.delete(synchronize_session=False)
  else:
    count = AuditLog.query.filter(AuditLog.project_id.in_(project_ids)).delete(synchronize_session=False)
  return {'audit_entries_deleted': count}


def _clear_projects(db, project_ids, models, upload_root):
  """Delete projects and every related module."""
  Project = models['Project']
  summary = {}
  for key in _PROJECT_MODULE_KEYS:
    summary[key] = clear_module_data(db, key, list(project_ids), upload_root, models)
  deleted = Project.query.filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
  summary['projects_deleted'] = deleted
  return summary


_MODULE_CLEARERS = {
  'documents': _clear_documents,
  'drawings': _clear_drawings,
  'rfis': _clear_rfis,
  'change_orders': _clear_change_orders,
  'commitments': _clear_commitments,
  'budget': _clear_budget,
  'pay_apps': _clear_pay_apps,
  'submittals': _clear_submittals,
  'punch_list': _clear_punch_list,
  'daily_log': _clear_daily_log,
  'weekly_report': _clear_weekly_report,
  'safety': _clear_safety,
  'schedule': _clear_schedule,
  'deliveries': _clear_deliveries,
  'inspections': _clear_inspections,
  'meeting_minutes': _clear_meeting_minutes,
  'photos': _clear_photos,
  'project_assets': _clear_project_assets,
  'sage_sync': _clear_sage_sync,
  'projects': _clear_projects,
  'companies': _clear_companies,
  'audit_log': None,  # special — needs all_projects flag
}


def clear_module_data(db, module_key: str, project_ids: list[int], upload_root: str, models: dict, *, all_projects: bool = False):
  """Clear one module for the given project ids. Returns a stats dict."""
  key = (module_key or '').strip().lower()
  if key not in _MODULE_CLEARERS:
    raise ValueError(f'Unknown maintenance module: {module_key}')
  if key == 'companies':
    return _clear_companies(db, project_ids, models, upload_root)
  if key == 'audit_log':
    return _clear_audit_log(db, project_ids, models, upload_root, all_projects=all_projects)
  if not project_ids:
    return {'skipped': True, 'reason': 'no projects'}
  fn = _MODULE_CLEARERS[key]
  return fn(db, project_ids, models, upload_root)


def clear_modules_batch(db, module_keys: list[str], project_ids: list[int], upload_root: str, models: dict, *, all_projects: bool = False):
  """Clear multiple modules; returns per-module results."""
  results = {}
  for key in module_keys:
    k = (key or '').strip().lower()
    if not k:
      continue
    results[k] = clear_module_data(db, k, project_ids, upload_root, models, all_projects=all_projects)
  return results


def build_models_dict(app_models: dict):
  """Map of model names used by maintenance clearers."""
  required = [
    'Project', 'Document', 'DocumentFolder', 'DocumentShareLink', 'DocumentFolderShareLink',
    'DocumentVersion', 'DocumentComment', 'DocumentActivity', 'DocumentMarkup', 'DocumentFolderPermission',
    'Drawing', 'DrawingRevision', 'DrawingMarkup', 'RFI',     'ChangeOrder', 'ChangeOrderAllocation',
    'ChangeOrderRevision', 'PotentialChangeOrder', 'PCOAllocation',
    'ChangeEvent', 'SubcontractorRFQ', 'RFQAllocation', 'ChangeOrderRequest', 'CORAllocation',
    'Commitment', 'CommitmentAllocation',
    'BudgetProjectState', 'PayAppProjectState', 'Submittal', 'PunchItem', 'DailyLog', 'ManpowerEntry',
    'EquipmentEntry', 'WeeklyReport', 'SafetyReport', 'SafetyCertification', 'SafetyTrainingEvent',
    'ScheduleData', 'ScheduleTask', 'Delivery', 'PermitInspectionItem', 'MeetingMinute', 'MeetingActionItem',
    'Photo', 'SageSyncEvent', 'Company', 'COI', 'AuditLog',
  ]
  out = {}
  for name in required:
    if name in app_models:
      out[name] = app_models[name]
  return out
