"""Load a module by file path under a unique name -- every idea folder has its own
`strategy.py`, so plain `import strategy` picks whichever folder is first on sys.path."""
import importlib.util, os


def load(path, name=None):
    path = os.path.abspath(path)
    name = name or "m_" + os.path.basename(os.path.dirname(path)).replace("-", "_") + "_" + os.path.basename(path)[:-3]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
