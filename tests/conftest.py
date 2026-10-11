import sys
import pytest
from termflex.lemmatizers import morph_backends as mb


@pytest.fixture
def clean_registry(monkeypatch):
    """Tests may register backends and import throwaway modules; undo all of it afterwards."""
    registry, instances = dict(mb._REGISTRY), dict(mb._INSTANCES)
    modules, path = set(sys.modules), list(sys.path)
    monkeypatch.setattr(mb, "_PLUGINS_LOADED", True)     # never scan the real installed entry points
    yield mb
    mb._REGISTRY.clear(); mb._REGISTRY.update(registry)
    mb._INSTANCES.clear(); mb._INSTANCES.update(instances)
    for name in set(sys.modules) - modules:
        del sys.modules[name]
    sys.path[:] = path


@pytest.fixture
def glossary_cwd(tmp_path_factory, monkeypatch):
    """Run from a directory holding an (empty) g.tbx, since the CLI checks the glossary exists up front."""
    d = tmp_path_factory.mktemp("glossary")
    (d / "g.tbx").write_text("<martif/>", encoding="utf-8")
    monkeypatch.chdir(d)
    return d
