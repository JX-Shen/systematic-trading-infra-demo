from __future__ import annotations

import builtins
import importlib
import sys
import unittest


class PlatformImportTests(unittest.TestCase):
    def test_runner_import_does_not_require_posix_termios(self) -> None:
        original_import = builtins.__import__
        sys.modules.pop("interview_demo.runner", None)

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in {"termios", "tty"}:
                raise ModuleNotFoundError(name)
            return original_import(name, globals, locals, fromlist, level)

        try:
            builtins.__import__ = guarded_import
            module = importlib.import_module("interview_demo.runner")
        finally:
            builtins.__import__ = original_import
            sys.modules.pop("interview_demo.runner", None)
            importlib.import_module("interview_demo.runner")

        self.assertTrue(hasattr(module, "Stepper"))


if __name__ == "__main__":
    unittest.main()
