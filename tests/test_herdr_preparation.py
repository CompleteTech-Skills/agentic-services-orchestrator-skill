"""Run the preserved helper regressions within the integrated package."""
import importlib.util
from pathlib import Path
import sys
import unittest

HELPERS = Path(__file__).resolve().parents[1] / "adapters" / "herdr" / "scripts"


def load_tests(loader, tests, pattern):
    sys.path.insert(0, str(HELPERS))
    try:
        spec = importlib.util.spec_from_file_location("bundled_herdr_tests", HELPERS / "test_prepare_run.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return loader.loadTestsFromModule(module)
    finally:
        sys.path.remove(str(HELPERS))


if __name__ == "__main__":
    unittest.main()
