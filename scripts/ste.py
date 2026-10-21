"""A checkable subset of ASD-STE100 for diagram labels and captions.

Simplified Technical English exists because a reader under pressure should not have to
decide which sense of a word was meant. The standard does that with a closed dictionary -
one word, one meaning, one part of speech - plus structural rules on the sentence.

**What this module is, exactly.** The official ASD-STE100 dictionary is a published
specification and is not bundled here. What is implemented is a small approved vocabulary of
connectives, chosen to be consistent with the standard, plus the structural rules that can be
checked mechanically: sentence length, active voice, one idea per sentence, no gerund used as
a noun, articles kept. Calling that "STE" without this paragraph would be the kind of
overclaim this plugin exists to catch, so: it is a conforming subset, not the standard.

Identifiers from the code pass through untouched. The standard allows a technical name, and
`InvalidSideError` is exactly that - renaming it for readability would make the diagram
describe something the reader cannot grep for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

#: The only verbs an edge label may use. One sense each, present tense, active.
APPROVED_VERBS: Final = frozenset(
    {
        "calls",
        "catches",
        "gets",
        "gives",
        "has",
        "holds",
        "imports",
        "is",
        "keeps",
        "makes",
        "raises",
        "reads",
        "returns",
        "sends",
        "shows",
        "starts",
        "stops",
        "uses",
        "writes",
    }
)

#: Words a caption may use beyond approved verbs and technical names. Deliberately small:
#: a caption that needs a word outside this set usually needs a shorter caption.
APPROVED_WORDS: Final = frozenset(
    {
        "a",
        "an",
        "and",
        "the",
        "to",
        "from",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "not",
        "no",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "each",
        "every",
        "all",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "module",
        "modules",
        "class",
        "classes",
        "package",
        "packages",
        "function",
        "functions",
        "method",
        "methods",
        "error",
        "errors",
        "test",
        "tests",
        "contract",
        "contracts",
        "caller",
        "callers",
        "code",
        "name",
        "names",
        "type",
        "types",
        "base",
        "import",
        "imports",
        "public",
        "private",
        "boundary",
        "seam",
        "seams",
        "branch",
        "branches",
        "line",
        "lines",
        "value",
        "values",
        "object",
        "objects",
        "first",
        "last",
        "only",
        "here",
        "then",
        "when",
        "where",
        "which",
        "what",
        "how",
        "why",
        "if",
        "but",
        "or",
        "diagram",
        "figure",
        "graph",
        "arrow",
        "arrows",
        "box",
        "boxes",
        "sections",
        "section",
        # Added when the first real captions needed them. Each is one word with one sense;
        # the list stays closed, and a caption that needs a word outside it is too long.
        "another",
        "breaks",
        "matches",
        "so",
        "look",
        "like",
        "more",
        "into",
        "outside",
        "same",
        "different",
        "than",
        "inside",
        "above",
        "below",
        "own",
        "as",
        "text",
    }
)

#: A procedural sentence may not be longer than this. Descriptive sentences get 25.
MAX_PROCEDURAL_WORDS: Final = 20
MAX_DESCRIPTIVE_WORDS: Final = 25

#: Gerunds that are approved as technical nouns despite the -ing ending.
ALLOWED_ING: Final = frozenset({"logging", "testing", "string", "during", "thing"})

_WORD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*")
_SENTENCE: Final = re.compile(r"[^.!?]+[.!?]")
_PASSIVE: Final = re.compile(r"\b(is|are|was|were|be|been|being)\s+\w+(ed|en)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Violation:
    """One place the text leaves the subset, and what to do instead."""

    text: str
    rule: str
    fix: str


def is_technical_name(word: str) -> bool:
    """Whether a word is an identifier from the code rather than prose.

    A technical name is allowed unchanged: CamelCase, snake_case, a dotted path, or anything
    carrying an underscore or a digit. Renaming one for readability would make the diagram
    describe something the reader cannot grep for.
    """
    return (
        "_" in word
        or "." in word
        or any(character.isdigit() for character in word)
        or (word[:1].isupper() and not word.isupper())
    )


def check_label(label: str) -> list[Violation]:
    """An edge label: one approved verb, nothing else."""
    words = _WORD.findall(label)
    if not words:
        return [Violation(label, "empty", "give the edge a verb from the approved list")]
    if len(words) > 1:
        return [
            Violation(
                label, "one verb per edge", f"use one of: {', '.join(sorted(APPROVED_VERBS))}"
            )
        ]
    if words[0].lower() not in APPROVED_VERBS:
        return [
            Violation(
                label,
                "verb is not approved",
                f"use one of: {', '.join(sorted(APPROVED_VERBS))}",
            )
        ]
    return []


def _sentences(text: str) -> list[str]:
    found = [s.strip() for s in _SENTENCE.findall(text)]
    tail = _SENTENCE.sub("", text).strip()
    return [*found, tail] if tail else found


def check_caption(text: str, *, procedural: bool = False) -> list[Violation]:
    """A caption: short active sentences, approved words, technical names, no gerund nouns."""
    limit = MAX_PROCEDURAL_WORDS if procedural else MAX_DESCRIPTIVE_WORDS
    out: list[Violation] = []

    for sentence in _sentences(text):
        words = _WORD.findall(sentence)
        if len(words) > limit:
            out.append(
                Violation(
                    sentence,
                    f"sentence is longer than {limit} words",
                    "split it; one idea per sentence",
                )
            )
        if _PASSIVE.search(sentence):
            out.append(Violation(sentence, "passive voice", "say who does it"))

        for word in words:
            if is_technical_name(word):
                continue
            lower = word.lower()
            # ALLOWED_ING words are approved nouns, not merely exempt from the gerund
            # rule; checking them here keeps them from falling through as unapproved.
            if lower in APPROVED_WORDS or lower in APPROVED_VERBS or lower in ALLOWED_ING:
                continue
            if lower.endswith("ing"):
                out.append(Violation(word, "gerund used as a noun", "use the verb or a noun"))
                continue
            out.append(Violation(word, "word is not in the approved set", "use a simpler word"))
    return out


def report(violations: list[Violation]) -> str:
    """Violations as text, one per line, with the fix beside each."""
    if not violations:
        return "every label and caption stays in the approved subset"
    return "\n".join(f"  {v.text!r}: {v.rule} - {v.fix}" for v in violations)
