"""Source-checkout compatibility entry point; the installed plugin is plugin/."""
import importlib.util
import runpy
import sys
from pathlib import Path

_payload = Path(__file__).resolve().parent / "plugin" / Path(__file__).name
if __name__ == "__main__":
    runpy.run_path(str(_payload), run_name="__main__")
else:
    _spec = importlib.util.spec_from_file_location(__name__, _payload)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[__name__] = _module
    _spec.loader.exec_module(_module)
