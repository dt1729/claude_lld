"""Behaviour of the anti-pattern detector, exercised through detect()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from detect_patterns import BLOCK, JUDGE, detect, format_report

ROOT_MODULE = Path("src/pkg/thing.py")
SUBFOLDER_MODULE = Path("src/pkg/lib/thing.py")


def rules(source: str, path: Path = ROOT_MODULE) -> list[int]:
    return [f.rule for f in detect(source, path)]


def verdict_of(source: str, rule: int, path: Path = ROOT_MODULE) -> str:
    return next(f.verdict for f in detect(source, path) if f.rule == rule)


# --- 1: singleton accessor --------------------------------------------------------------


def test_classmethod_returning_cached_instance_blocks() -> None:
    src = """
class Pool:
    _instance = None

    @classmethod
    def instance(cls):
        return cls._instance
"""
    assert 1 in rules(src)
    assert verdict_of(src, 1) == BLOCK


def test_global_assigned_inside_function_blocks() -> None:
    src = """
CACHE = None

def warm():
    global CACHE
    CACHE = 1
"""
    assert 1 in rules(src)


def test_ordinary_classmethod_constructor_is_clean() -> None:
    src = """
class Pool:
    @classmethod
    def from_dsn(cls, dsn: str) -> "Pool":
        return cls(dsn)
"""
    assert 1 not in rules(src)


# --- 2: module-level mutable state ------------------------------------------------------


def test_mutated_module_dict_blocks() -> None:
    src = """
SEEN = {}

def note(key: str) -> None:
    SEEN[key] = 1
"""
    assert 2 in rules(src)


def test_unmutated_module_constant_is_clean() -> None:
    """A read-only table is not state; flagging it would train people to ignore the rule."""
    src = """
BACKENDS = {"yolo": 1, "rtdetr": 2}

def pick(name: str) -> int:
    return BACKENDS[name]
"""
    assert 2 not in rules(src)


# --- 3: import-time side effects --------------------------------------------------------


def test_bare_module_level_call_blocks() -> None:
    assert 3 in rules("load_model('big.pt')\n")


def test_pure_module_level_call_is_clean() -> None:
    src = """
from pathlib import Path
ROOT = Path("/tmp")
"""
    assert 3 not in rules(src)


def test_module_level_assignment_from_unknown_call_is_judged() -> None:
    src = "CONFIG = load_settings()\n"
    assert verdict_of(src, 3) == JUDGE


# --- 4, 5: inheritance ------------------------------------------------------------------


def test_inheriting_own_concrete_class_blocks() -> None:
    src = """
class Reader:
    def read(self) -> int:
        return 1

class CachedReader(Reader):
    pass
"""
    assert 4 in rules(src)


def test_inheriting_own_abstract_base_is_clean() -> None:
    src = """
from abc import ABC, abstractmethod

class Transport(ABC):
    def send_with_retry(self, b: bytes) -> None:
        self._send_once(b)

    @abstractmethod
    def _send_once(self, b: bytes) -> None: ...

class Tcp(Transport):
    def _send_once(self, b: bytes) -> None:
        pass
"""
    assert 4 not in rules(src)


def test_three_level_chain_reports_depth() -> None:
    src = """
from abc import ABC, abstractmethod

class Base(ABC):
    @abstractmethod
    def go(self) -> None: ...

class Middle(Base):
    def go(self) -> None:
        pass

class Leaf(Middle):
    pass
"""
    assert 5 in rules(src)


# --- 6, 7, 9: class shapes --------------------------------------------------------------


def test_all_abstract_abc_blocks() -> None:
    src = """
from abc import ABC, abstractmethod

class Store(ABC):
    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def load(self) -> None: ...
"""
    assert 6 in rules(src)


def test_abc_with_shared_implementation_is_clean() -> None:
    src = """
from abc import ABC, abstractmethod

class Store(ABC):
    def save_all(self, items: list[int]) -> None:
        for i in items:
            self.save(i)

    @abstractmethod
    def save(self, item: int) -> None: ...
"""
    assert 6 not in rules(src)


def test_stateful_mixin_blocks() -> None:
    src = """
class LoggingMixin:
    def __init__(self) -> None:
        self._log = 1
"""
    assert 7 in rules(src)


def test_stateless_mixin_is_clean() -> None:
    src = """
class ComparableMixin:
    def __lt__(self, other: object) -> bool:
        return True
"""
    assert 7 not in rules(src)


def test_all_staticmethod_class_blocks() -> None:
    src = """
class MathUtils:
    @staticmethod
    def add(a: int, b: int) -> int:
        return a + b

    @staticmethod
    def sub(a: int, b: int) -> int:
        return a - b
"""
    assert 9 in rules(src)


# --- 8, 10: shapes that need judgment ---------------------------------------------------


def test_class_with_init_and_one_method_is_judged_not_blocked() -> None:
    src = """
class ReportGenerator:
    def __init__(self, run: int) -> None:
        self._run = run

    def generate(self) -> str:
        return str(self._run)
"""
    assert verdict_of(src, 8) == JUDGE


def test_dataclass_with_one_method_is_not_flagged_as_function() -> None:
    src = """
from dataclasses import dataclass

@dataclass(frozen=True)
class Point:
    x: int

    def shifted(self) -> int:
        return self.x + 1
"""
    assert 8 not in rules(src)


def test_pass_through_wrapper_is_judged() -> None:
    src = """
def get_user(uid: str) -> int:
    return repo_get_user(uid)
"""
    assert verdict_of(src, 10) == JUDGE


def test_wrapper_that_adds_an_argument_is_clean() -> None:
    src = """
def get_user(uid: str) -> int:
    return repo_get_user(uid, timeout_s=5)
"""
    assert 10 not in rules(src)


# --- 12: stringly-typed mode ------------------------------------------------------------


def test_str_param_compared_twice_is_judged() -> None:
    src = """
def run(mode: str) -> int:
    if mode == "fast":
        return 1
    if mode == "accurate":
        return 2
    return 0
"""
    assert verdict_of(src, 12) == JUDGE


def test_str_param_compared_once_is_clean() -> None:
    src = """
def run(name: str) -> int:
    if name == "":
        return 0
    return 1
"""
    assert 12 not in rules(src)


# --- 13: environment reads --------------------------------------------------------------


def test_env_read_in_library_module_blocks() -> None:
    src = """
import os

def threshold() -> str:
    return os.getenv("THRESH", "0.5")
"""
    assert 13 in rules(src)


def test_env_read_in_composition_root_is_clean() -> None:
    src = """
import os

def load() -> str:
    return os.getenv("THRESH", "0.5")
"""
    assert 13 not in rules(src, Path("src/pkg/cli.py"))


# --- 14: mutable value objects ----------------------------------------------------------


def test_mutable_dataclass_in_root_module_is_judged() -> None:
    src = """
from dataclasses import dataclass

@dataclass
class Settings:
    threshold: float
"""
    assert verdict_of(src, 14) == JUDGE


def test_frozen_dataclass_is_clean() -> None:
    src = """
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Settings:
    threshold: float
"""
    assert 14 not in rules(src)


def test_mutable_dataclass_in_subfolder_is_clean() -> None:
    """Private modules make no promise, so the rule does not apply there."""
    src = """
from dataclasses import dataclass

@dataclass
class Accumulator:
    total: int
"""
    assert 14 not in rules(src, SUBFOLDER_MODULE)


# --- 15: barrel __init__ ----------------------------------------------------------------


def test_init_with_imports_blocks() -> None:
    src = "from pkg.thing import run\n"
    assert 15 in rules(src, Path("src/pkg/__init__.py"))


def test_empty_init_is_clean() -> None:
    assert 15 not in rules('"""Package."""\n', Path("src/pkg/__init__.py"))


# --- reporting and failure modes --------------------------------------------------------


def test_clean_file_reports_nothing() -> None:
    src = """
def add(a: int, b: int) -> int:
    return a + b
"""
    assert detect(src, ROOT_MODULE) == []
    assert format_report([]) == "no anti-patterns detected"


def test_findings_are_ordered_by_line() -> None:
    src = """
import os

SEEN = {}

def note(k: str) -> None:
    SEEN[k] = os.getenv(k, "")
"""
    lines = [f.line for f in detect(src, ROOT_MODULE)]
    assert lines == sorted(lines)


def test_report_puts_blocking_findings_first() -> None:
    src = """
class Pool:
    _instance = None

    @classmethod
    def instance(cls):
        return cls._instance

def wrap(x: int) -> int:
    return inner(x)
"""
    report = format_report(detect(src, ROOT_MODULE))
    assert report.index("BLOCKING") < report.index("NEEDS JUDGMENT")


def test_unparseable_source_raises_syntaxerror() -> None:
    with pytest.raises(SyntaxError):
        detect("def broken(:\n", ROOT_MODULE)
