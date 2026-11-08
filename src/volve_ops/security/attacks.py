"""The parser and archive attack corpus of protocol section 22.5.

The defences already exist. `safe_xml` refuses DTDs, entities, external references and XInclude
behind a size and extension allow-list, and `safe_archive` refuses path escape, symlink members,
absolute and ratio-based decompression bombs, member counts and case-or-normalisation
collisions. Both were written in an early phase. Phase 7 does not write them; it attacks them,
which is a different activity and the only one that produces evidence.

Every fixture is generated here rather than committed as a binary, so a reader can see exactly
what each one contains. Nothing points at a real file: the entity and traversal fixtures name
paths under a directory that does not exist, so a fixture that somehow succeeds produces a loud
failure rather than reading anything.

One honest limit. The absolute decompression budgets are 32 GiB total and 4 GiB per member, and
generating a fixture that large to prove a bound is not a reasonable test. Those two are
exercised against lowered budgets passed to the same code path, which tests the comparison and
not the constant. The constants themselves are asserted separately, so a change to either is
visible.
"""

from __future__ import annotations

import random
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: A path that does not exist, named by every fixture that tries to read a file. If one of these
#: ever succeeds the failure is unmistakable, which a reference to /etc/passwd would not be: that
#: file exists, and a test that read it would look like a test that passed.
UNREACHABLE: Final[str] = "/nonexistent-volve-security-fixture/secret.txt"

XML_HEADER: Final[str] = '<?xml version="1.0"?>'


@dataclass(frozen=True)
class Attack:
    """One hostile input, what it attempts, and what must refuse it."""

    name: str
    attempts: str
    build: Callable[[Path], Path]
    """Writes the fixture under the given directory and returns its path."""

    expect_refusal_mentioning: tuple[str, ...] = ()
    """Substrings the refusal should contain, lowercased. Empty where the message is not fixed."""


# --- XML -------------------------------------------------------------------------------------


def _write(directory: Path, name: str, text: str, *, encoding: str = "utf-8") -> Path:
    path = directory / name
    path.write_text(text, encoding=encoding)
    return path


def _external_entity_file(d: Path) -> Path:
    return _write(
        d,
        "external_entity_file.xml",
        f'{XML_HEADER}<!DOCTYPE r [<!ENTITY x SYSTEM "file://{UNREACHABLE}">]><r>&x;</r>',
    )


def _external_entity_http(d: Path) -> Path:
    return _write(
        d,
        "external_entity_http.xml",
        f"{XML_HEADER}<!DOCTYPE r [<!ENTITY x SYSTEM "
        f'"http://127.0.0.1:1/volve-fixture">]><r>&x;</r>',
    )


def _recursive_entity(d: Path) -> Path:
    """The billion-laughs shape, kept small.

    The parser must refuse the construct rather than survive the expansion.
    """
    entities = "".join(f'<!ENTITY e{i} "&e{i - 1};&e{i - 1};">' for i in range(1, 10))
    return _write(
        d,
        "recursive_entity.xml",
        f'{XML_HEADER}<!DOCTYPE r [<!ENTITY e0 "volve">{entities}]><r>&e9;</r>',
    )


def _parameter_entity(d: Path) -> Path:
    return _write(
        d,
        "parameter_entity.xml",
        f'{XML_HEADER}<!DOCTYPE r [<!ENTITY % p SYSTEM "file://{UNREACHABLE}">%p;]><r/>',
    )


def _external_dtd(d: Path) -> Path:
    return _write(
        d,
        "external_dtd.xml",
        f'{XML_HEADER}<!DOCTYPE r SYSTEM "http://127.0.0.1:1/volve.dtd"><r/>',
    )


def _xinclude_local_file(d: Path) -> Path:
    """Parses harmlessly today; the danger is any later code reaching for ElementInclude."""
    return _write(
        d,
        "xinclude_local.xml",
        f'{XML_HEADER}<r xmlns:xi="http://www.w3.org/2001/XInclude">'
        f'<xi:include href="{UNREACHABLE}" parse="text"/></r>',
    )


def _nested_xinclude(d: Path) -> Path:
    """The include is not at the root, so a check that looked only at the root would miss it."""
    return _write(
        d,
        "xinclude_nested.xml",
        f'{XML_HEADER}<r xmlns:xi="http://www.w3.org/2001/XInclude"><a><b>'
        f'<xi:include href="{UNREACHABLE}"/></b></a></r>',
    )


def _encoding_mismatch(d: Path) -> Path:
    """Declares UTF-8 and is written in UTF-16, so the declaration and the bytes disagree.

    **This one parses, and should.** It sits in `PARSES_CORRECTLY` rather than among the attacks.
    Section 11.3 asks for encoding variants and the obvious guess is that a mismatched
    declaration is an attack; against this parser it is not. The encoding trick is a way to
    smuggle characters past a filter that inspects content, and `safe_xml` refuses constructs
    rather than filtering content, so there is no filter to get past. Expat resolves the encoding
    from the byte-order mark and returns the document's true text.

    Asserting the real behaviour is worth more than asserting a refusal that would never come.
    """
    path = d / "encoding_mismatch.xml"
    path.write_bytes(f"{XML_HEADER}<r>drilling</r>".encode("utf-16"))
    return path


def _malformed(d: Path) -> Path:
    return _write(d, "malformed.xml", f"{XML_HEADER}<r><unclosed></r>")


def _oversized(d: Path) -> Path:
    """Past the size allow-list. Written just over a lowered bound by the test that uses it."""
    return _write(d, "oversized.xml", f"{XML_HEADER}<r>{'x' * 20_000}</r>")


def _disallowed_extension(d: Path) -> Path:
    return _write(d, "report.txt", f"{XML_HEADER}<r/>")


XML_ATTACKS: Final[tuple[Attack, ...]] = (
    Attack(
        "external-entity-file",
        "read a local file through an external entity",
        _external_entity_file,
        ("entit",),
    ),
    Attack(
        "external-entity-http",
        "fetch a remote URL through an external entity",
        _external_entity_http,
        ("entit",),
    ),
    Attack(
        "recursive-entity",
        "exhaust memory with recursive internal entities",
        _recursive_entity,
        ("entit",),
    ),
    Attack(
        "parameter-entity", "read a local file through a parameter entity", _parameter_entity, ()
    ),
    Attack("external-dtd", "make parsing depend on a remote host", _external_dtd, ("dtd",)),
    Attack(
        "xinclude-local-file",
        "read a local file through XInclude",
        _xinclude_local_file,
        ("xinclude",),
    ),
    Attack(
        "xinclude-nested",
        "hide an XInclude below the root element",
        _nested_xinclude,
        ("xinclude",),
    ),
    Attack(
        "malformed",
        "exercise the malformed path, which must quarantine rather than crash",
        _malformed,
        ("malformed",),
    ),
    Attack("oversized", "parse a document past the size allow-list", _oversized, ("limit",)),
    Attack(
        "disallowed-extension",
        "parse a document outside the extension allow-list",
        _disallowed_extension,
        ("extension",),
    ),
)


# --- archives --------------------------------------------------------------------------------


def _zip_with(directory: Path, name: str, members: dict[str, str]) -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return path


def _relative_escape(d: Path) -> Path:
    return _zip_with(d, "relative_escape.zip", {"../../escaped.xml": "<r/>"})


def _absolute_member(d: Path) -> Path:
    return _zip_with(d, "absolute_member.zip", {"/tmp/absolute.xml": "<r/>"})


def _drive_prefixed(d: Path) -> Path:
    return _zip_with(d, "drive_prefixed.zip", {"C:windows/evil.xml": "<r/>"})


def _url_scheme_member(d: Path) -> Path:
    return _zip_with(d, "url_scheme.zip", {"http://host/evil.xml": "<r/>"})


def _symlink_member(d: Path) -> Path:
    """A symlink member, which can redirect a later write even when its own path looks safe."""
    path = d / "symlink_member.zip"
    with zipfile.ZipFile(path, "w") as archive:
        info = zipfile.ZipInfo("link.xml")
        # 0xA1FF: symlink, mode 0777, in the high bits where zip keeps unix permissions.
        info.external_attr = 0xA1FF << 16
        archive.writestr(info, UNREACHABLE)
    return path


def _case_collision(d: Path) -> Path:
    return _zip_with(d, "case_collision.zip", {"Report.xml": "<r/>", "report.xml": "<r/>"})


def _nfc_collision(d: Path) -> Path:
    """Two names that are different byte sequences and the same filename after NFC.

    The pair matters and the first version of this fixture got it wrong: it used U+00F8, the
    o-slash, against an o with a combining diaeresis. Those are different letters, they never
    collide, and the fixture asserted a refusal that correctly never came. Written as code points
    below so the pair cannot be misread: a decomposed and a precomposed form of the same letter.
    """
    decomposed = "rappo\u0308rt.xml"
    precomposed = "rapp\u00f6rt.xml"
    return _zip_with(d, "nfc_collision.zip", {decomposed: "<r/>", precomposed: "<r/>"})


def _too_many_members(d: Path) -> Path:
    return _zip_with(d, "many_members.zip", {f"m{i}.xml": "<r/>" for i in range(40)})


def _high_ratio_member(d: Path) -> Path:
    """Highly compressible content, sized so only the ratio bound can refuse it.

    The first version was two megabytes, which the absolute per-member budget caught first. That
    is the better defence and the module says so, but it meant the ratio check never fired and
    was never exercised. This one sits under the lowered member budget the test passes and well
    over the lowered ratio.
    """
    return _zip_with(d, "high_ratio.zip", {"bomb.xml": "A" * 400_000})


def _oversized_member(d: Path) -> Path:
    """Past the absolute per-member budget, which is the bound that matters most."""
    return _zip_with(d, "oversized_member.zip", {"big.xml": "A" * 2_000_000})


def _incompressible(length: int, seed: int) -> bytes:
    """Deterministic bytes that deflate cannot shrink.

    A fixture for the total budget has to be incompressible, or the ratio check refuses it first
    and the budget is never reached. Repeated characters compress about a thousand to one, which
    is how the first version of `_oversized_total` ended up proving the ratio bound twice.
    Seeded, so the fixture is the same on every run.
    """
    return random.Random(seed).randbytes(length)


def _oversized_total(d: Path) -> Path:
    """Each member under the per-member budget; together over the archive's total budget."""
    path = d / "oversized_total.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for i in range(4):
            archive.writestr(f"p{i}.bin", _incompressible(400_000, seed=i))
    return path


ARCHIVE_ATTACKS: Final[tuple[Attack, ...]] = (
    Attack("relative-escape", "escape the destination with ..", _relative_escape, ("escape",)),
    Attack("absolute-member", "write to an absolute path", _absolute_member, ()),
    Attack("drive-prefixed", "write to a drive-prefixed path", _drive_prefixed, ()),
    Attack("url-scheme-member", "name a member with a URL scheme", _url_scheme_member, ()),
    Attack(
        "symlink-member", "redirect a later write with a symlink", _symlink_member, ("symlink",)
    ),
    Attack(
        "case-collision", "collide two members under case folding", _case_collision, ("collide",)
    ),
    Attack(
        "nfc-collision",
        "collide two members under Unicode normalisation",
        _nfc_collision,
        ("collide",),
    ),
    Attack("too-many-members", "exceed the member count", _too_many_members, ("members",)),
    Attack(
        "high-ratio-member", "expand far past its compressed size", _high_ratio_member, ("ratio",)
    ),
    Attack(
        "oversized-member", "exceed the absolute per-member budget", _oversized_member, ("expands",)
    ),
    Attack("oversized-total", "exceed the archive's total budget", _oversized_total, ("total",)),
)

#: Inputs that are odd but not hostile, and must be read correctly rather than refused. A corpus
#: holding only things that must fail cannot tell a parser that refuses attacks from one that
#: refuses everything, so the corpus carries both.
PARSES_CORRECTLY: Final[tuple[Attack, ...]] = (
    Attack(
        "encoding-mismatch",
        "declare one encoding and use another; expat resolves it from the byte-order mark",
        _encoding_mismatch,
        (),
    ),
)

ALL_ATTACKS: Final[tuple[Attack, ...]] = (*XML_ATTACKS, *ARCHIVE_ATTACKS)
