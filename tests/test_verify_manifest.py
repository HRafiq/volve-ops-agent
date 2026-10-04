"""Manifest scanning and verification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from verify_manifest import read_manifest, sha256_of, verify, walk


def _data(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _manifest(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / "manifest.md"
    path.write_text(
        "| File | Source path or URL | Kind | Size (bytes) | SHA-256 | Retrieved | Used by |\n"
        "|---|---|---|---|---|---|---|\n" + rows,
        encoding="utf-8",
    )
    return path


def test_an_empty_manifest_verifies_as_nothing_to_do(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    assert verify(root, _manifest(tmp_path, "")) == 0


def test_matching_file_verifies(tmp_path: Path) -> None:
    root = tmp_path / "data"
    f = _data(root, "a.csv", "x,y\n1,2\n")
    rows = f"| a.csv | url | csv | {f.stat().st_size} | {sha256_of(f)} | 2026-10-04 | tests |\n"
    assert verify(root, _manifest(tmp_path, rows)) == 0


def test_changed_bytes_are_detected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    f = _data(root, "a.csv", "x,y\n1,2\n")
    rows = f"| a.csv | url | csv | {f.stat().st_size} | {sha256_of(f)} | 2026-10-04 | tests |\n"
    manifest = _manifest(tmp_path, rows)
    f.write_text("x,y\n9,9\n", encoding="utf-8")
    assert verify(root, manifest) == 1


def test_missing_and_unrecorded_files_are_both_reported(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    rows = "| gone.csv | url | csv | 10 | " + "0" * 64 + " | 2026-10-04 | tests |\n"
    _data(root, "extra.csv", "surprise\n")
    assert verify(root, _manifest(tmp_path, rows)) == 1


def test_manifest_prose_is_not_parsed_as_rows(tmp_path: Path) -> None:
    """The manifest holds descriptive tables too; only well-formed file rows count."""
    manifest = _manifest(tmp_path, "| Licence | to be recorded after review |\n")
    recorded, unparsed = read_manifest(manifest)
    assert recorded == {}
    assert unparsed == []


def test_a_row_that_looks_like_a_file_row_but_does_not_parse_fails_verification(
    tmp_path: Path,
) -> None:
    """Format drift must not turn verification into a silent no-op that still exits zero."""
    root = tmp_path / "data"
    root.mkdir()
    # Size written with a thousands separator: plausible drift, and the regex will not match.
    rows = "| a.csv | url | csv | 1,024 | " + "a" * 64 + " | 2026-10-04 | tests |\n"
    manifest = _manifest(tmp_path, rows)
    recorded, unparsed = read_manifest(manifest)
    assert recorded == {}
    assert len(unparsed) == 1
    assert verify(root, manifest) == 1


def test_an_uppercase_checksum_still_matches(tmp_path: Path) -> None:
    root = tmp_path / "data"
    f = _data(root, "a.csv", "x,y\n1,2\n")
    sha = sha256_of(f).upper()
    rows = f"| a.csv | url | csv | {f.stat().st_size} | {sha} | 2026-10-04 | tests |\n"
    assert verify(root, _manifest(tmp_path, rows)) == 0


def test_dotted_paths_are_skipped_consistently_at_every_depth(tmp_path: Path) -> None:
    """Testing only the leaf name leaves dot-directory contents visible to half the tool."""
    root = tmp_path / "data"
    _data(root, ".hidden.csv", "a\n")
    _data(root, ".cache/inside.csv", "b\n")
    _data(root, "visible.csv", "c\n")
    rows_out: list[str] = []
    for path in walk(root):
        rows_out.append(path.relative_to(root).as_posix())
    assert rows_out == ["visible.csv"]
