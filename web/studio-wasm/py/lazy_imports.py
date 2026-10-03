"""Packages the studio's worker imports but doesn't run, fetched only if it ever does (docs/WEB-STUDIO.md, "On the
device", "A quicker start"). The program imports scipy and soundfile at the top of its synthesis modules, which the
studio's questions import (a version's sound, its arrangement, its players) but never call: only a render does, and
renders are made in render workers of their own, which load every package. So the studio's worker (studio-worker.mjs,
its "control" start) loads numpy alone and installs this first: `import scipy...` and `from scipy.signal import
sosfilt` then give stand-ins, and nothing is fetched (scipy's wheel is 13 MiB: nearly half of what the worker fetched).

- A stand-in called by a module as it is imported (`GLIDE_SHAPE = PchipInterpolator(...)` in the voice) gives a
  stand-in for what the call makes, made by that same call when it is first used.
- A stand-in used for real (called from a function, or looked into) raises Needed: not an Exception, so the studio's
  own handlers, which say every Exception as an answer, let it through to the worker, which fetches the package
  (Pyodide's loadPackage), calls real(), and asks the same question again. From then on every stand-in is the thing
  itself, looked up (or made) on first use.

Nothing a stand-in stands for is ever computed differently: it is the package's own object, or nothing.

    install(["scipy", "soundfile"])   before the program is imported
    real("scipy")                     once the package is loaded: the stand-ins become it
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
import types

_LAZY: set[str] = set()


class Needed(BaseException):  # noqa: N818 - a signal to the worker, not an error
    """A package a stand-in needs: the worker fetches it and asks again."""

    def __init__(self, package: str):
        super().__init__(package)
        self.package = package


def _top(name: str) -> str:
    return name.partition(".")[0]


def _named(module: str, names: tuple[str, ...]):
    thing = importlib.import_module(module)
    for name in names:
        thing = getattr(thing, name)
    return thing


class _Stand:
    """What `from scipy.signal import sosfilt` gives here: the real thing, looked up (or made) when first used."""

    __slots__ = ("_package", "_make", "_what", "_real", "_made")

    def __init__(self, package: str, make, what: str):
        for k, v in (("_package", package), ("_make", make), ("_what", what), ("_real", None), ("_made", False)):
            object.__setattr__(self, k, v)

    def _waiting(self) -> bool:
        return not object.__getattribute__(self, "_made") and object.__getattribute__(self, "_package") in _LAZY

    def _thing(self):
        if not object.__getattribute__(self, "_made"):
            package = object.__getattribute__(self, "_package")
            if package in _LAZY:
                raise Needed(package)
            object.__setattr__(self, "_real", object.__getattribute__(self, "_make")())
            object.__setattr__(self, "_made", True)
            object.__setattr__(self, "_make", None)
        return object.__getattribute__(self, "_real")

    def __getattr__(self, name: str):
        if _Stand._waiting(self):
            if name.startswith("__") and name.endswith("__"):  # asked of it, not used (hasattr, inspect)
                raise AttributeError(name)
            # `from scipy import fft` then `fft.rfft`: a stand-in for that too
            return _Stand(object.__getattribute__(self, "_package"), lambda: getattr(_Stand._thing(self), name),
                          f"{object.__getattribute__(self, '_what')}.{name}")
        return getattr(_Stand._thing(self), name)

    def __call__(self, *args, **kwargs):
        if _Stand._waiting(self) and sys._getframe(1).f_code.co_name == "<module>":  # a module's table, as it's imported
            return _Stand(object.__getattribute__(self, "_package"), lambda: _Stand._thing(self)(*args, **kwargs),
                          f"{object.__getattribute__(self, '_what')}(...)")
        return _Stand._thing(self)(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<stand-in for {object.__getattribute__(self, '_what')}>"


def _used(name: str):
    def use(self, *args, **kwargs):
        return getattr(_Stand._thing(self), name)(*args, **kwargs)
    use.__name__ = name
    return use


# what Python looks up on the type, not through __getattr__: each makes the thing first
for _name in ("__iter__", "__len__", "__getitem__", "__contains__", "__array__", "__float__", "__int__", "__index__",
              "__bool__", "__lt__", "__le__", "__gt__", "__ge__", "__add__", "__radd__", "__sub__", "__rsub__",
              "__mul__", "__rmul__", "__truediv__", "__rtruediv__", "__neg__", "__pow__", "__matmul__"):
    setattr(_Stand, _name, _used(_name))


class _Module(types.ModuleType):
    """A lazy package's module: each name in it a stand-in; submodules found by the finder below."""

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        module = self.__name__
        if _top(module) not in _LAZY:  # the package has come: the module itself, now
            return getattr(importlib.import_module(module), name)
        return _Stand(_top(module), lambda: _named(module, (name,)), f"{module}.{name}")


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _top(name) in _LAZY:
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        module = _Module(spec.name)
        module.__path__ = []
        return module

    def exec_module(self, module) -> None:
        pass


_FINDER = _Finder()


def install(packages) -> None:
    """Stand-ins for these packages' modules from now on (before anything imports them)."""
    _LAZY.update(packages)
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)


def real(package: str) -> None:
    """The package is loaded: its stand-in modules go, and every stand-in becomes what it stands for when next used."""
    _LAZY.discard(package)
    for name in [n for n, m in sys.modules.items() if _top(n) == package and isinstance(m, _Module)]:
        del sys.modules[name]
    if not _LAZY and _FINDER in sys.meta_path:
        sys.meta_path.remove(_FINDER)


def lazy() -> list[str]:
    """The packages still stood in for."""
    return sorted(_LAZY)
