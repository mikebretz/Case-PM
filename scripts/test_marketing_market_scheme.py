"""Apply construction market scheme idempotently (no duplicate landing slug)."""
import sys
import unittest

sys.path.insert(0, '/workspace')


class MarketingMarketSchemeTests(unittest.TestCase):
    def test_apply_scheme_twice_no_integrity_error(self):
        from app import app, db, _marketing_models
        from marketing_construction_markets import apply_construction_market_scheme
        from marketing_persistence import ensure_marketing_schema

        with app.app_context():
            ensure_marketing_schema(db)
            apply_construction_market_scheme(db, _marketing_models, 'commercial')
            db.session.commit()
            apply_construction_market_scheme(db, _marketing_models, 'residential')
            db.session.commit()


if __name__ == '__main__':
    unittest.main()
