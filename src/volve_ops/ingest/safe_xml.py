"""Hardened XML parsing.

Drilling reports arrive as XML from outside the project, so the parser is a trust boundary.
Three attacks are closed here, by refusing the features they need rather than by
pattern-matching payloads:

- external entity expansion, which turns a parser into a file reader or an HTTP client;
- recursive internal entities, the billion-laughs shape, which exhausts memory;
- external DTD retrieval, which makes parsing depend on a remote host.

A document needing any of those is rejected, and there is no flag to allow it.

A fourth, XInclude, is not an attack on this function but is a loaded gun left on the table.
Nothing here resolves includes, so a document containing one parses harmlessly. But
xml.etree.ElementInclude.include() on the returned tree would read whatever href names,
including a local file. Any later code that reaches for ElementInclude to assemble a
multi-part report reopens the file-read primitive this module exists to close. Include
elements are therefore refused outright, so the returned tree cannot carry one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final
from xml.etree.ElementTree import Element  # types only; all parsing goes through defusedxml

from defusedxml.common import DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden
from defusedxml.ElementTree import ParseError as DefusedParseError
from defusedxml.ElementTree import parse as defused_parse

from volve_ops.ingest.quarantine import UnsafeInputError

# A parsed tree runs roughly an order of magnitude larger than its source bytes, so this cap
# is about resident memory rather than disk. Eight mebibytes of report XML is already far
# larger than a daily drilling report; a file over it is either not what it claims to be or
# should be streamed with an element budget instead of parsed whole.
MAX_XML_BYTES: Final[int] = 8 * 1024 * 1024

ALLOWED_XML_SUFFIXES: Final[frozenset[str]] = frozenset({".xml"})

XINCLUDE_NAMESPACE: Final[str] = "{http://www.w3.org/2001/XInclude}"


def parse_xml_file(path: Path, *, max_bytes: int = MAX_XML_BYTES) -> Element:
    """Parse one XML file with entities, DTDs and external references refused.

    Raises UnsafeInputError for an unsafe or malformed document, including one whose size or
    extension falls outside the allow-list. Filesystem failures propagate as OSError: a file
    that cannot be read is an operational problem, not a hostile document, and recording it
    as one would quarantine perfectly good data.
    """
    resolved = path.resolve()

    if resolved.suffix.lower() not in ALLOWED_XML_SUFFIXES:
        raise UnsafeInputError(f"not an allowed XML extension: {resolved.name}")

    if not resolved.is_file():
        raise UnsafeInputError(f"not a regular file: {resolved}")

    size = resolved.stat().st_size
    if size > max_bytes:
        raise UnsafeInputError(f"file is {size} bytes, over the {max_bytes} byte limit")

    try:
        tree = defused_parse(
            str(resolved),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden) as exc:
        # Keep the message: it names the entity or system id, which is what a human needs.
        # forbid_dtd rejects any DOCTYPE, so this also fires on a harmless internal subset.
        raise UnsafeInputError(f"refused XML in {resolved.name}: {exc}") from exc
    except DefusedParseError as exc:
        raise UnsafeInputError(f"malformed XML in {resolved.name}: {exc}") from exc

    root = tree.getroot()
    if not isinstance(root, Element):  # pragma: no cover - defensive against an untyped parser
        raise UnsafeInputError(f"no element at the root of {resolved.name}")

    if root.tag.startswith(XINCLUDE_NAMESPACE) or any(
        element.tag.startswith(XINCLUDE_NAMESPACE)
        for element in root.iter()
        if isinstance(element.tag, str)
    ):
        raise UnsafeInputError(f"XInclude element in {resolved.name}")

    return root
