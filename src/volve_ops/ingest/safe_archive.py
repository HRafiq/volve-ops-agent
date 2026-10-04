"""Hardened archive extraction.

Archive handling is the other place where reading someone else's bytes can write to places of
their choosing. Guards, in the order a member meets them:

- a member path that escapes the destination, by "..", by an absolute path, or by a drive or
  scheme prefix, which is the zip-slip family;
- a symlink member, which can redirect a later write even when its own path looks safe;
- a member or archive that decompresses past an absolute budget, which is the zip-bomb
  family, with a ratio check as a secondary signal;
- more members than the archive should plausibly hold;
- two members whose names differ only in case or in Unicode normalisation, which collide into
  one file on macOS and Windows.

Extraction goes to a temporary directory beside the destination and is moved into place only
once every member is written, so a failure part-way leaves nothing behind.

Two deliberate limits. Only symlinks are inspected among non-regular members, which is
sufficient because extraction never calls os.symlink: a symlink member is written as an
ordinary file holding the link text, so the failure mode is a corrupt file rather than an
escape. And nested archives are not unpacked. A recursive extractor is a new attack surface
and nothing in this project needs one, so a zip inside a zip is written as a file and left
alone.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Final

from volve_ops.ingest.quarantine import UnsafeInputError

# Absolute budgets are the real bomb defence. These are sized to the envelope this project
# actually ingests, not to the largest thing a filesystem could hold.
MAX_UNCOMPRESSED_BYTES: Final[int] = 32 * 1024 * 1024 * 1024
MAX_MEMBER_BYTES: Final[int] = 4 * 1024 * 1024 * 1024
MAX_MEMBERS: Final[int] = 100_000

# Ratio is a secondary signal only, and the bar is high on purpose. Structurally repetitive
# XML, which is what a production or drilling log is, deflates far better than prose: a
# multi-megabyte file of repeated rows measured about 250 to 1 in testing, so a limit near
# that would reject real data as hostile. Deflate's theoretical ceiling is about 1032 to 1,
# so 900 still catches a true bomb while leaving ordinary XML alone.
MAX_COMPRESSION_RATIO: Final[float] = 900.0

COPY_CHUNK: Final[int] = 1024 * 1024

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")


def _collision_key(name: str) -> str:
    """Key under which two member names would collide on a real filesystem."""
    return unicodedata.normalize("NFC", name).casefold()


def _check_member_path(name: str, resolved_destination: Path) -> Path:
    """Resolve an archive member path and refuse anything that escapes the destination."""
    if not name or name.strip("/") in {"", ".", ".."}:
        raise UnsafeInputError(f"archive member has no usable name: {name!r}")
    if name.startswith("/") or name.startswith("\\"):
        raise UnsafeInputError(f"absolute path in archive member: {name!r}")
    if _WINDOWS_DRIVE.match(name) or _URL_SCHEME.match(name):
        raise UnsafeInputError(f"drive or scheme prefix in archive member: {name!r}")
    if any(part == ".." for part in name.replace("\\", "/").split("/")):
        raise UnsafeInputError(f"parent traversal in archive member: {name!r}")
    if "\x00" in name:
        raise UnsafeInputError(f"null byte in archive member: {name!r}")

    target = (resolved_destination / name).resolve()
    if target == resolved_destination or resolved_destination not in target.parents:
        raise UnsafeInputError(f"archive member escapes destination: {name!r}")
    return target


def _validate(
    infos: list[zipfile.ZipInfo],
    resolved_destination: Path,
    *,
    max_total_bytes: int,
    max_member_bytes: int,
    max_members: int,
    max_ratio: float,
) -> None:
    """Reject the whole archive if any member is unsafe. Writes nothing."""
    if len(infos) > max_members:
        raise UnsafeInputError(f"archive has {len(infos)} members, over {max_members}")

    seen: dict[str, str] = {}
    total = 0

    for info in infos:
        _check_member_path(info.filename, resolved_destination)

        key = _collision_key(info.filename)
        if key in seen:
            raise UnsafeInputError(
                f"archive members {seen[key]!r} and {info.filename!r} collide on a "
                "case-insensitive or normalisation-insensitive filesystem"
            )
        seen[key] = info.filename

        # Mode bits live in the top 16 of external_attr. S_IFLNK is 0o120000.
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) == 0o120000:
            raise UnsafeInputError(f"symlink in archive member: {info.filename!r}")

        if info.file_size > max_member_bytes:
            raise UnsafeInputError(f"member {info.filename!r} expands to {info.file_size} bytes")

        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > max_ratio:
                raise UnsafeInputError(
                    f"member {info.filename!r} compression ratio {ratio:.0f} "
                    f"exceeds {max_ratio:.0f}"
                )

        total += info.file_size
        if total > max_total_bytes:
            raise UnsafeInputError(f"archive expands to over {max_total_bytes} bytes in total")


def safe_extract_zip(
    archive: Path,
    destination: Path,
    *,
    max_total_bytes: int = MAX_UNCOMPRESSED_BYTES,
    max_member_bytes: int = MAX_MEMBER_BYTES,
    max_members: int = MAX_MEMBERS,
    max_ratio: float = MAX_COMPRESSION_RATIO,
) -> list[Path]:
    """Extract a zip archive, refusing unsafe members. Returns the files written.

    Every member is validated before any is written, and writing happens in a temporary
    directory that is moved into the destination only on success, so neither a hostile member
    nor a disk error leaves a partial tree.

    Raises UnsafeInputError for an unsafe or unreadable archive, including a write failure:
    once bytes are coming from an archive, a filesystem refusal is part of its behaviour.
    """
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()

    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            _validate(
                infos,
                resolved_destination,
                max_total_bytes=max_total_bytes,
                max_member_bytes=max_member_bytes,
                max_members=max_members,
                max_ratio=max_ratio,
            )

            staging = Path(tempfile.mkdtemp(prefix=".extract-", dir=resolved_destination))
            try:
                written_relative: list[str] = []
                for info in infos:
                    if info.is_dir():
                        continue
                    # Validated against the destination above; staging is inside it.
                    target = staging / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # "xb" so a collision the validator missed fails loudly, never silently.
                    with zf.open(info) as src, target.open("xb") as dst:
                        shutil.copyfileobj(src, dst, COPY_CHUNK)
                    written_relative.append(info.filename)

                written: list[Path] = []
                for relative in written_relative:
                    final = resolved_destination / relative
                    final.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(staging / relative), str(final))
                    written.append(final)
                return written
            finally:
                shutil.rmtree(staging, ignore_errors=True)

    except zipfile.BadZipFile as exc:
        raise UnsafeInputError(f"not a readable zip archive: {archive.name}: {exc}") from exc
    except OSError as exc:
        raise UnsafeInputError(f"failed while extracting {archive.name}: {exc}") from exc
