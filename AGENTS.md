# Case PM

Single-file Flask app (`app.py`) for construction project management. Uses Flask-SQLAlchemy with a SQLite database at `instance/case_pm.db`, Flask-Login for auth, and Jinja templates in `templates/`.

## Cursor Cloud specific instructions

- Python 3.12 with a virtualenv at `venv/`. Dependencies are in `requirements.txt`; the startup update script keeps them installed. Run tooling via `./venv/bin/python`.
- Run the app in dev mode: `./venv/bin/python app.py` (Flask dev server on `0.0.0.0:5000`, debug + auto-reload on). There is no separate build step.
- On first run, `app.py`'s `__main__` block calls `db.create_all()` and seeds a default admin (`admin@casepm.local` / `admin123`) if missing. This seeding/table creation only happens when running `python app.py` directly, not on `import`.
- The default admin has `must_change_password=True`, so the first login forces a password change before the dashboard is reachable.
- Creating a project requires at least one row in the `Company` table: the "Client / Owner" `<select>` is HTML-`required` and is populated only from existing companies. Seed one if needed, e.g. `./venv/bin/python -c "from app import app, db, Company; app.app_context().push(); db.session.add(Company(name='Acme Corp', type='Client / Owner')); db.session.commit()"`.
- There are no automated tests or linter configs in this repo. Use `./venv/bin/python -m py_compile app.py` as a quick syntax/compile check.
- `instance/case_pm.db` is committed and tracked; avoid committing local test data written to it during manual testing.
