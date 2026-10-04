"""Compute and verify checksums for the files recorded in docs/data_manifest.md.

The manifest is the project's claim about what the results rest on. A claim nobody can
check is decoration, so this script does both halves of the job: it produces the rows to
paste into the manifest when data is first retrieved, and afterwards it re-reads them and
reports any file whose bytes no longer match.

Run it from the repository root, since the default manifest path is relative to it.

Usage:

    python scripts/verify_manifest.py scan data/raw          # emit manifest rows
    python scripts/verify_manifest.py verify data/raw        # check against the manifest

Raw data is never committed, so this runs against a local tree and prints its findings
rather than writing anything into the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Iterator
from pathlib import Path

CHUNK = 1024 * 1024
MANIFEST = Path("docs/data_manifest.md")

# A manifest file row: | path | source | kind | size | sha256 | retrieved | used by |
ROW = re.compile(
    r"^\|\s*(?P<path>[^|]+?)\s*\|[^|]*\|[^|]*\|\s*(?P<size>\d+)\s*\|"
    r"\s*(?P<sha>[0-9a-fA-F]{64})\s*\|"
)

# Anything that looks like it was meant to be a file row. Used to tell a legitimately empty
# manifest apart from a format drift that silently turned verification into a no-op, which
# would otherwise report success forever.
CANDIDATE = re.compile(r"^\|.*\|.*\|.*\|.*\|.*\|")
SKIP = re.compile(r"^\|[\s|:-]*$")
HEADER_WORDS = ("File", "Source path")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def walk(root: Path) -> Iterator[Path]:
    """Yield every regular file under root, skipping dotted paths at any depth.

    The dot test covers every path component, not just the leaf: testing the leaf alone
    leaves files inside a dot-directory visible to one half of the tool and not the other.
    Symlinks are skipped rather than followed, so a link is never checksummed as if it were
    data.
    """
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def scan(root: Path) -> int:
    """Print one manifest row per file, ready to paste."""
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    count = 0
    for path in walk(root):
        rel = path.relative_to(root).as_posix()
        print(
            f"| {rel} | TODO source path | {path.suffix.lstrip('.') or 'none'} "
            f"| {path.stat().st_size} | {sha256_of(path)} | TODO date | TODO |"
        )
        count += 1
    print(f"\n{count} file(s) under {root}", file=sys.stderr)
    return 0


def read_manifest(manifest: Path) -> tuple[dict[str, tuple[int, str]], list[str]]:
    """Return the recorded files and any candidate row that failed to parse.

    A row that looks like a file row but does not match is returned rather than ignored.
    Silently skipping it is how a changed column order turns verification into a no-op that
    still exits zero.
    """
    recorded: dict[str, tuple[int, str]] = {}
    unparsed: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or SKIP.match(stripped):
            continue
        if any(word in stripped for word in HEADER_WORDS):
            continue
        match = ROW.match(stripped)
        if match:
            recorded[match["path"]] = (int(match["size"]), match["sha"].lower())
        elif CANDIDATE.match(stripped):
            unparsed.append(stripped)
    return recorded, unparsed


def verify(root: Path, manifest: Path = MANIFEST) -> int:
    """Compare a local tree against the manifest. Non-zero exit on any mismatch."""
    if not manifest.is_file():
        print(f"manifest not found: {manifest}", file=sys.stderr)
        return 2

    recorded, unparsed = read_manifest(manifest)

    if unparsed:
        print(f"{len(unparsed)} row(s) in {manifest} look like file rows but did not parse:")
        for row in unparsed:
            print(f"  UNPARSED {row[:120]}")
        print("Verification refuses to report success on a manifest it cannot read.")
        return 1

    if not recorded:
        print(f"{manifest} records no files yet; nothing to verify", file=sys.stderr)
        print("EMPTY-MANIFEST")
        return 0

    present = {p.relative_to(root).as_posix(): p for p in walk(root)}
    problems = 0

    for rel, (size, sha) in sorted(recorded.items()):
        path = present.get(rel)
        if path is None:
            print(f"MISSING  {rel}")
            problems += 1
            continue
        actual_size = path.stat().st_size
        if actual_size != size:
            print(f"SIZE     {rel}: manifest {size}, found {actual_size}")
            problems += 1
            continue
        actual_sha = sha256_of(path)
        if actual_sha != sha.lower():
            print(f"CHECKSUM {rel}: manifest {sha}, found {actual_sha}")
            problems += 1
        else:
            print(f"ok       {rel}")

    for rel in sorted(set(present) - set(recorded)):
        print(f"UNRECORDED {rel}")
        problems += 1

    print(f"\n{len(recorded)} recorded, {problems} problem(s)", file=sys.stderr)
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["scan", "verify"])
    parser.add_argument("root", type=Path, help="local directory holding the retrieved data")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)

    if args.action == "scan":
        return scan(args.root)
    return verify(args.root, args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
