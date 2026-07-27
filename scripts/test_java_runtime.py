"""Tests for bundled Java runtime resolution."""
import unittest


class JavaRuntimeTests(unittest.TestCase):
    def test_java_runtime_status_on_linux(self):
        from java_runtime import java_runtime_status

        status = java_runtime_status()
        self.assertIn('ok', status)
        self.assertIn('jvm_path', status)
        # CI/dev Linux images should have Java available.
        self.assertTrue(status['ok'], status)

    def test_resolve_jvm_path(self):
        from java_runtime import resolve_jvm_path

        jvm = resolve_jvm_path()
        self.assertTrue(jvm)
        self.assertTrue(jvm.endswith(('.so', '.dll', '.dylib')))

    def test_mpp_import_uses_java_runtime(self):
        from schedule_mpp_import import mpp_import_status

        status = mpp_import_status()
        self.assertTrue(status['packages_ok'])
        self.assertTrue(status['available'], status)


if __name__ == '__main__':
    unittest.main()
