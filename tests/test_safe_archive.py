"""Archive extraction hardening."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from volve_ops.ingest.quarantine import UnsafeInputError
from volve_ops.ingest.safe_archive import safe_extract_zip

SYMLINK_MODE = (0o120000 | 0o777) << 16


def _zip_with(tmp_path: Path, members: dict[str, str], name: str = "a.zip") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, body in members.items():
            zf.writestr(member, body)
    return path


def test_extracts_benign_members(tmp_path: Path) -> None:
    archive = _zip_with(tmp_path, {"a.xml": "<r/>", "sub/b.xml": "<r/>"})
    out = tmp_path / "out"
    written = safe_extract_zip(archive, out)
    assert {p.relative_to(out).as_posix() for p in written} == {"a.xml", "sub/b.xml"}
    assert (out / "sub" / "b.xml").read_text() == "<r/>"


@pytest.mark.parametrize(
    "member",
    [
        "../escape.xml",
        "sub/../../escape.xml",
        "/etc/passwd",
        "..\\escape.xml",
    ],
)
def test_rejects_members_that_escape_the_destination(tmp_path: Path, member: str) -> None:
    archive = _zip_with(tmp_path, {member: "x"})
    with pytest.raises(UnsafeInputError):
        safe_extract_zip(archive, tmp_path / "out")


def test_rejects_symlink_members(tmp_path: Path) -> None:
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("link")
        info.external_attr = SYMLINK_MODE
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(UnsafeInputError, match="symlink"):
        safe_extract_zip(archive, tmp_path / "out")


def test_rejects_a_highly_compressible_bomb(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("z", "0" * 40_000_000)
    with pytest.raises(UnsafeInputError, match="compression ratio"):
        safe_extract_zip(archive, tmp_path / "out")


def test_accepts_the_compression_ratio_ordinary_production_xml_reaches(tmp_path: Path) -> None:
    """Repetitive XML deflates far better than prose, around 250 to 1 when measured.

    A ratio limit near that would reject real data as an attack, so the absolute size caps
    are the bomb defence and the ratio is only a secondary signal.
    """
    row = "  <row><well>15/9-F-1</well><oil uom='Sm3'>1234.5</oil></row>\n"
    archive = tmp_path / "plain.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("log.xml", "<log>\n" + row * 20_000 + "</log>")

    with zipfile.ZipFile(archive) as zf:
        info = zf.infolist()[0]
        measured = info.file_size / info.compress_size
    assert measured > 200, f"expected repetitive XML to exceed 200:1, measured {measured:.0f}"

    assert len(safe_extract_zip(archive, tmp_path / "out")) == 1


def test_rejects_member_over_the_per_member_limit(tmp_path: Path) -> None:
    archive = _zip_with(tmp_path, {"a.xml": "x" * 4096})
    with pytest.raises(UnsafeInputError, match="expands to"):
        safe_extract_zip(archive, tmp_path / "out", max_member_bytes=1024, max_ratio=1e9)


def test_rejects_archive_over_the_total_limit(tmp_path: Path) -> None:
    archive = _zip_with(tmp_path, {"a.xml": "x" * 800, "b.xml": "y" * 800})
    with pytest.raises(UnsafeInputError, match="in total"):
        safe_extract_zip(archive, tmp_path / "out", max_total_bytes=1000, max_ratio=1e9)


def test_rejects_archive_with_too_many_members(tmp_path: Path) -> None:
    archive = _zip_with(tmp_path, {f"f{i}.xml": "x" for i in range(10)})
    with pytest.raises(UnsafeInputError, match="members"):
        safe_extract_zip(archive, tmp_path / "out", max_members=5)


def test_writes_nothing_when_a_later_member_is_unsafe(tmp_path: Path) -> None:
    """Validation runs over every member before the first byte is written."""
    archive = _zip_with(tmp_path, {"good.xml": "<r/>", "../evil.xml": "x"})
    out = tmp_path / "out"
    with pytest.raises(UnsafeInputError):
        safe_extract_zip(archive, out)
    assert not (out / "good.xml").exists()


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Report.XML", "report.xml"),
        ("cafe\u0301.xml", "caf\u00e9.xml"),
    ],
)
def test_rejects_members_that_collide_on_a_real_filesystem(
    tmp_path: Path, first: str, second: str
) -> None:
    """On macOS and Windows these become one file holding the second member's bytes.

    Left alone it is worse than data loss: the manifest would record a checksum under one
    name for another file's content, which is exactly the provenance claim this project makes.
    """
    archive = _zip_with(tmp_path, {first: "one", second: "two"})
    with pytest.raises(UnsafeInputError, match="collide"):
        safe_extract_zip(archive, tmp_path / "out")


@pytest.mark.parametrize("member", [".", "", "./", ".."])
def test_rejects_members_with_no_usable_name(tmp_path: Path, member: str) -> None:
    archive = tmp_path / "odd.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(zipfile.ZipInfo(member), "x")
    with pytest.raises(UnsafeInputError):
        safe_extract_zip(archive, tmp_path / "out")


def test_allows_a_colon_in_an_iso_timestamp_filename(tmp_path: Path) -> None:
    """Exported data often names files by timestamp; that is not a drive prefix."""
    archive = _zip_with(tmp_path, {"2010-06-01T12:00:00.xml": "<r/>"})
    out = tmp_path / "out"
    assert len(safe_extract_zip(archive, out)) == 1


@pytest.mark.parametrize("member", ["C:/evil.xml", "http://host/evil.xml"])
def test_still_rejects_drive_and_scheme_prefixes(tmp_path: Path, member: str) -> None:
    archive = _zip_with(tmp_path, {member: "x"})
    with pytest.raises(UnsafeInputError):
        safe_extract_zip(archive, tmp_path / "out")


def test_a_write_failure_leaves_nothing_behind_and_raises_the_declared_error(
    tmp_path: Path,
) -> None:
    """A regular file followed by a directory of the same name fails mid-write."""
    archive = _zip_with(tmp_path, {"first.xml": "<r/>", "sub": "x", "sub/b.xml": "y"})
    out = tmp_path / "out"
    with pytest.raises(UnsafeInputError):
        safe_extract_zip(archive, out)
    assert sorted(p.name for p in out.rglob("*")) == []


def test_rejects_a_file_that_is_not_a_zip(tmp_path: Path) -> None:
    path = tmp_path / "not.zip"
    path.write_text("plain text")
    with pytest.raises(UnsafeInputError, match="readable zip"):
        safe_extract_zip(path, tmp_path / "out")
