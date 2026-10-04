"""XML parser hardening.

Attack documents are built here rather than committed, so the repository never ships
hostile files, and so each test states the shape it defends against in the one place a
reader will look when it fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from volve_ops.ingest.quarantine import UnsafeInputError
from volve_ops.ingest.safe_xml import parse_xml_file


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_a_benign_document(tmp_path: Path) -> None:
    path = _write(tmp_path, "report.xml", "<report><well>15/9-F-1</well></report>")
    root = parse_xml_file(path)
    assert root.tag == "report"
    assert root.findtext("well") == "15/9-F-1"


def test_rejects_external_entity_that_would_read_a_local_file(tmp_path: Path) -> None:
    secret = _write(tmp_path, "secret.txt", "credentials")
    body = (
        "<?xml version='1.0'?>" f"<!DOCTYPE r [<!ENTITY x SYSTEM 'file://{secret}'>]>" "<r>&x;</r>"
    )
    path = _write(tmp_path, "xxe.xml", body)
    with pytest.raises(UnsafeInputError):
        parse_xml_file(path)


def test_rejects_recursive_entity_expansion(tmp_path: Path) -> None:
    body = (
        "<?xml version='1.0'?>"
        "<!DOCTYPE lol ["
        "<!ENTITY a 'aaaaaaaaaa'>"
        "<!ENTITY b '&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;'>"
        "<!ENTITY c '&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;'>"
        "]>"
        "<lol>&c;</lol>"
    )
    path = _write(tmp_path, "bomb.xml", body)
    with pytest.raises(UnsafeInputError):
        parse_xml_file(path)


def test_rejects_external_dtd_reference(tmp_path: Path) -> None:
    body = "<?xml version='1.0'?><!DOCTYPE r SYSTEM 'http://example.invalid/r.dtd'><r/>"
    path = _write(tmp_path, "dtd.xml", body)
    with pytest.raises(UnsafeInputError):
        parse_xml_file(path)


def test_rejects_malformed_document_without_weakening_validation(tmp_path: Path) -> None:
    path = _write(tmp_path, "broken.xml", "<report><well>unclosed")
    with pytest.raises(UnsafeInputError):
        parse_xml_file(path)


def test_rejects_an_xinclude_element(tmp_path: Path) -> None:
    """Not an attack on the parser, but a file-read primitive left in the returned tree.

    Nothing here resolves includes, so this document parses harmlessly today. A later phase
    reaching for ElementInclude to assemble a multi-part report would reopen the hole, so the
    element never reaches the caller.
    """
    body = (
        "<r xmlns:xi='http://www.w3.org/2001/XInclude'>"
        "<xi:include href='/etc/hosts' parse='text'/>"
        "</r>"
    )
    path = _write(tmp_path, "xinclude.xml", body)
    with pytest.raises(UnsafeInputError, match="XInclude"):
        parse_xml_file(path)


def test_a_refusal_keeps_the_detail_a_human_needs(tmp_path: Path) -> None:
    """forbid_dtd rejects any DOCTYPE, so the system id is what tells the two cases apart."""
    body = "<!DOCTYPE r SYSTEM 'http://example.invalid/r.dtd'><r/>"
    path = _write(tmp_path, "detail.xml", body)
    with pytest.raises(UnsafeInputError, match="example.invalid"):
        parse_xml_file(path)


def test_an_unreadable_file_is_an_operational_error_not_a_hostile_document(
    tmp_path: Path,
) -> None:
    """Reporting a permissions failure as unsafe would quarantine perfectly good data."""
    path = _write(tmp_path, "noperm.xml", "<r/>")
    path.chmod(0o000)
    try:
        with pytest.raises(OSError):
            parse_xml_file(path)
    finally:
        path.chmod(0o600)


def test_rejects_file_over_the_size_limit(tmp_path: Path) -> None:
    path = _write(tmp_path, "big.xml", "<r>" + ("x" * 4096) + "</r>")
    with pytest.raises(UnsafeInputError, match="over the"):
        parse_xml_file(path, max_bytes=1024)


def test_rejects_extension_outside_the_allow_list(tmp_path: Path) -> None:
    path = _write(tmp_path, "report.txt", "<r/>")
    with pytest.raises(UnsafeInputError, match="extension"):
        parse_xml_file(path)


def test_rejects_a_directory_and_a_missing_path(tmp_path: Path) -> None:
    directory = tmp_path / "d.xml"
    directory.mkdir()
    with pytest.raises(UnsafeInputError, match="regular file"):
        parse_xml_file(directory)
    with pytest.raises(UnsafeInputError, match="regular file"):
        parse_xml_file(tmp_path / "absent.xml")
