from __future__ import annotations

import unittest


class PackageFacadeTest(unittest.TestCase):
    def test_analytics_and_legacy_metrics_import_same_functions(self):
        from fcn_wizard.analytics.metrics import fair_coupon_proxy as organized
        from fcn_wizard.metrics import fair_coupon_proxy as legacy

        self.assertIs(legacy, organized)

    def test_storage_and_legacy_run_storage_import_same_functions(self):
        from fcn_wizard.run_storage import save_run_table as legacy
        from fcn_wizard.storage.run_storage import save_run_table as organized

        self.assertIs(legacy, organized)

    def test_data_and_legacy_market_data_import_same_functions(self):
        from fcn_wizard.data.market_data import ib_duration as organized
        from fcn_wizard.market_data import ib_duration as legacy

        self.assertIs(legacy, organized)


if __name__ == "__main__":
    unittest.main()
