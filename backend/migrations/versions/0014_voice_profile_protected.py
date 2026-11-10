"""Protected voices: is_protected on voice_profiles

Revision ID: 0014_voice_profile_protected
Revises: 0013_generation_history_design_recipe
Create Date: 2026-11-10 00:00:00.000000

Adds ``voice_profiles.is_protected INTEGER DEFAULT 0``. A protected voice
refuses ``DELETE /profiles/{id}`` and ``PUT /profiles/{id}/audio`` with 409
until ``POST /profiles/{id}/protect`` lifts the flag — for the voices an
owner must never lose to a stray click (the Sado starter voices, a recording
of someone who cannot re-record).

Additive + idempotent (PRAGMA table_info guard, matching 0013); mirrored in
``core/db.py::_BASE_SCHEMA`` so fresh installs and migrated DBs converge, and
``_reconcile_additive_columns`` heals DBs where alembic cannot run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_voice_profile_protected"
down_revision: Union[str, None] = "0013_generation_history_design_recipe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    if not _has_table("voice_profiles"):
        return
    if not _has_column("voice_profiles", "is_protected"):
        op.add_column(
            "voice_profiles",
            sa.Column("is_protected", sa.Integer(), nullable=True, server_default="0"),
        )


def downgrade() -> None:
    if _has_table("voice_profiles") and _has_column("voice_profiles", "is_protected"):
        op.drop_column("voice_profiles", "is_protected")
