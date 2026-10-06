"""The version freeze of protocol section 19.1.

Section 12 already said a result without a complete manifest is not a result. This is the field list
made typed, so that the claim is enforced rather than remembered.

Two details carry the weight. A field whose value is legitimately absent records `none` rather than
being left out, because an omitted field and a deliberately empty one are different claims and a
reader cannot tell them apart from the output. And the hash is taken over the fields alone, so a
run repeated on unchanged inputs reproduces it: section 19.1 gates on that, because a version
freeze that does not reproduce is a record of nothing.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

ABSENT: Final[str] = "none"

#: Every field section 19.1 requires. Ordered, because the hash is taken over this order.
REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "dataset_version",
    "label_set_version",
    "parser_version",
    "extractor_version",
    "investigator_version",
    "retrieval_index_version",
    "correction_store_version",
    "model_roles",
    "commit",
)


class VersionFreeze(BaseModel):
    """What a scored run froze. Every field is required and none may be empty."""

    # `model_roles` is the field name protocol section 19.1 fixes, and pydantic reserves the
    # `model_` prefix. The protocol's name wins and the namespace is released here rather than
    # renaming a pre-registered field to silence a warning.
    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    dataset_version: str
    label_set_version: str
    parser_version: str
    extractor_version: str
    investigator_version: str
    retrieval_index_version: str
    correction_store_version: str
    model_roles: str
    commit: str

    @field_validator("*")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Refuse an empty field. `none` is how absence is recorded, deliberately and visibly."""
        if not value.strip():
            raise ValueError(
                "a version field may not be blank; record 'none' where the value is legitimately "
                "absent, so that absence is a claim rather than an omission"
            )
        return value

    @property
    def manifest_hash(self) -> str:
        """A digest over the fields in their declared order, stable across runs."""
        payload = json.dumps(
            {field: getattr(self, field) for field in REQUIRED_FIELDS},
            sort_keys=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def calls_a_model(self) -> bool:
        return self.model_roles != ABSENT


def current_commit(repo: Path | None = None) -> str:
    """The repository state, or `unknown` outside a checkout.

    Not an exception: a run in an exported tree is still a run, and refusing to produce a manifest
    because git is absent would make the manifest harder to produce than to omit.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def describe_model_roles(roles: Mapping[str, str | None]) -> str:
    """Render the role-to-model mapping, or `none` when no role is bound to a model.

    The roles are the semantic ones the plan fixes: extraction, investigation, judge, embedding.
    A role bound to nothing is rendered as such rather than dropped, so a reader can see which
    parts of the system were deterministic on this run.
    """
    if not roles or all(model is None for model in roles.values()):
        return ABSENT
    return ", ".join(f"{role}={model or ABSENT}" for role, model in sorted(roles.items()))


def missing_fields(freeze: Mapping[str, object]) -> tuple[str, ...]:
    """Which required fields a raw manifest is missing or has left blank.

    Takes a mapping rather than a `VersionFreeze` on purpose: this is what checks a manifest written
    by an earlier run, which is exactly the case where a field could be absent.
    """
    out: list[str] = []
    for field in REQUIRED_FIELDS:
        value = freeze.get(field)
        if value is None or not str(value).strip():
            out.append(field)
    return tuple(out)
