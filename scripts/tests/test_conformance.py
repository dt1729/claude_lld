"""Behaviour of the contract-conformance check, rule 37."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from conformance import conformance, contract_path_for, declarations, interface_block
from findings import BLOCK, JUDGE

CONTRACT = """# Contract: shapes.square

## Responsibility

Represent a square with a validated side length.

## Interface

```python
Square(side_m: float)
  .area_m2      -> float
  .perimeter_m  -> float
```

side_m is metres and always > 0.

## Seam

None.
"""

MODULE = '''"""A square."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Square:
    side_m: float

    @property
    def area_m2(self) -> float:
        return self.side_m**2

    @property
    def perimeter_m(self) -> float:
        return 4 * self.side_m
'''

FUNCTION_CONTRACT = """## Interface

```python
def load(path: Path, *, strict: bool) -> Config
```
"""


def names(contract: str = CONTRACT) -> list[str]:
    return [d.qualified for d in declarations(contract)]


def messages(contract: str, source: str) -> list[str]:
    return [f.message for f in conformance(contract, source)]


# --- reading the contract ------------------------------------------------------------------


def test_the_interface_block_is_extracted_from_its_section() -> None:
    assert interface_block(CONTRACT).startswith("Square(side_m: float)")


def test_prose_after_the_block_is_not_part_of_it() -> None:
    assert "metres" not in interface_block(CONTRACT)


def test_a_contract_with_no_interface_section_yields_nothing() -> None:
    assert interface_block("# Contract\n\n## Seam\n\nNone.\n") == ""


def test_a_constructor_and_its_members_are_declared() -> None:
    assert names() == ["Square", "Square.area_m2", "Square.perimeter_m"]


def test_a_function_signature_is_declared_with_its_parameters() -> None:
    declared = declarations(FUNCTION_CONTRACT)[0]
    assert declared.params == ["path", "strict"]
    assert declared.returns == "Config"


def test_prose_inside_the_block_is_skipped_rather_than_guessed_at() -> None:
    contract = (
        "## Interface\n\n```python\nSquare(side_m: float)\n# a comment\nnot a signature\n```\n"
    )
    assert names(contract) == ["Square"]


# --- agreement ------------------------------------------------------------------------------


def test_a_module_matching_its_contract_is_clean() -> None:
    assert conformance(CONTRACT, MODULE) == []


def test_a_contract_with_no_declarations_checks_nothing() -> None:
    """An Interface section of prose is a different defect, caught by validate_contract."""
    assert conformance("## Interface\n\nIt takes a square.\n", MODULE) == []


# --- disagreement ---------------------------------------------------------------------------


def test_a_promised_member_the_module_lacks_blocks() -> None:
    trimmed = MODULE.replace(
        "    @property\n    def perimeter_m(self) -> float:\n        return 4 * self.side_m\n", ""
    )
    found = conformance(CONTRACT, trimmed)
    assert [f.verdict for f in found] == [BLOCK]
    assert "Square.perimeter_m" in found[0].name


def test_a_promised_name_the_module_never_defines_blocks() -> None:
    assert any("does not define" in m for m in messages(FUNCTION_CONTRACT, MODULE))


def test_a_changed_constructor_signature_blocks() -> None:
    renamed = MODULE.replace("side_m: float", "side: float").replace("self.side_m", "self.side")
    assert any("constructed with ['side']" in m for m in messages(CONTRACT, renamed))


def test_a_changed_return_type_blocks() -> None:
    widened = MODULE.replace("def area_m2(self) -> float:", "def area_m2(self) -> int:")
    assert any("contract promises float" in m for m in messages(CONTRACT, widened))


def test_a_changed_parameter_list_blocks() -> None:
    source = "from pathlib import Path\n\n\ndef load(path: Path) -> object:\n    return path\n"
    assert any("parameters are ['path']" in m for m in messages(FUNCTION_CONTRACT, source))


# --- undocumented surface ---------------------------------------------------------------------


def test_a_public_name_the_contract_omits_is_judged() -> None:
    extra = MODULE + "\n\ndef diagonal(side_m: float) -> float:\n    return side_m * 1.414\n"
    found = [f for f in conformance(CONTRACT, extra) if f.verdict == JUDGE]
    assert [f.name for f in found] == ["diagonal"]


def test_a_private_name_is_not_undocumented_surface() -> None:
    extra = MODULE + "\n\ndef _diagonal(side_m: float) -> float:\n    return side_m\n"
    assert conformance(CONTRACT, extra) == []


# --- paths and failure modes -------------------------------------------------------------------


def test_a_module_maps_to_its_contract() -> None:
    assert contract_path_for(Path("src/shapes/square.py")) == Path(
        "docs/contracts/shapes.square.md"
    )


def test_an_unparseable_module_raises_syntaxerror() -> None:
    with pytest.raises(SyntaxError):
        conformance(CONTRACT, "def broken(:\n")


def test_findings_are_ordered_by_line() -> None:
    extra = MODULE + "\n\ndef diagonal(side_m: float) -> float:\n    return side_m\n"
    lines = [f.line for f in conformance(CONTRACT, extra)]
    assert lines == sorted(lines)
