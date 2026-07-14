"""Add planning metadata to tasks, task_dependencies, contact tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("tasks")]
    tables = inspector.get_table_names()
    tasks_fks = [fk["constrained_columns"] for fk in inspector.get_foreign_keys("tasks")]
    tasks_checks = [c["name"] for c in inspector.get_check_constraints("tasks")]
    tasks_indexes = [idx["name"] for idx in inspector.get_indexes("tasks")]

    # 1. Add columns to tasks table
    if "task_duration_min" not in columns:
        op.add_column("tasks", sa.Column("task_duration_min", sa.Integer(), nullable=True))
    if "earliest_start" not in columns:
        op.add_column("tasks", sa.Column("earliest_start", sa.DateTime(timezone=True), nullable=True))
    if "latest_end" not in columns:
        op.add_column("tasks", sa.Column("latest_end", sa.DateTime(timezone=True), nullable=True))
    if "hard_deadline" not in columns:
        op.add_column("tasks", sa.Column("hard_deadline", sa.DateTime(timezone=True), nullable=True))
    if "soft_deadline" not in columns:
        op.add_column("tasks", sa.Column("soft_deadline", sa.DateTime(timezone=True), nullable=True))
    if "labels" not in columns:
        op.add_column("tasks", sa.Column("labels", postgresql.ARRAY(sa.Text()), nullable=True, server_default=sa.text("'{}'")))
    if "template_id" not in columns:
        op.add_column("tasks", sa.Column("template_id", sa.UUID(), nullable=True))
    if "planning_state" not in columns:
        op.add_column("tasks", sa.Column("planning_state", sa.Text(), nullable=True))

    # 2. Add FK for template_id
    if ["template_id"] not in tasks_fks:
        op.create_foreign_key(
            "fk_tasks_template", "tasks", "tasks",
            ["template_id"], ["id"], ondelete="SET NULL"
        )

    # 3. Add CHECK constraint for planning_state
    if "ck_tasks_planning_state" not in tasks_checks:
        op.execute(
            "ALTER TABLE tasks ADD CONSTRAINT ck_tasks_planning_state "
            "CHECK (planning_state IS NULL OR planning_state IN "
            "('unscheduled', 'scheduled', 'in_progress', 'completed', 'blocked'))"
        )

    # 4. Create task_dependencies table
    created_task_deps = False
    if "task_dependencies" not in tables:
        op.create_table(
            "task_dependencies",
            sa.Column("parent_id", sa.UUID(), nullable=False),
            sa.Column("child_id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(["parent_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["child_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("parent_id", "child_id"),
            sa.CheckConstraint("parent_id != child_id", name="ck_task_dep_no_self_ref"),
        )
        created_task_deps = True

    # 5. Create contacts table
    if "contacts" not in tables:
        op.create_table(
            "contacts",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    # 6. Create contact_emails table
    if "contact_emails" not in tables:
        op.create_table(
            "contact_emails",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("email", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # 7. Create contact_phones table
    if "contact_phones" not in tables:
        op.create_table(
            "contact_phones",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("phone", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # 8. Create contact_addresses table
    if "contact_addresses" not in tables:
        op.create_table(
            "contact_addresses",
            sa.Column("id", sa.UUID(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    # 9. Create contact_sources table
    if "contact_sources" not in tables:
        op.create_table(
            "contact_sources",
            sa.Column("contact_id", sa.UUID(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("source_id", sa.Text(), nullable=True),
            sa.Column("etag", sa.Text(), nullable=True),
            sa.Column("last_sync", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("contact_id", "source", "source_id"),
        )

    # 10. GIN index on tasks.labels
    if "ix_tasks_labels_gin" not in tasks_indexes:
        op.create_index("ix_tasks_labels_gin", "tasks", ["labels"], postgresql_using="gin")

    # 11. Index on task_dependencies.child_id
    if created_task_deps:
        op.create_index("ix_task_dependencies_child_id", "task_dependencies", ["child_id"])
    else:
        dep_indexes = [idx["name"] for idx in inspector.get_indexes("task_dependencies")]
        if "ix_task_dependencies_child_id" not in dep_indexes:
            op.create_index("ix_task_dependencies_child_id", "task_dependencies", ["child_id"])


def downgrade() -> None:
    op.drop_index("ix_task_dependencies_child_id", table_name="task_dependencies")
    op.drop_index("ix_tasks_labels_gin", table_name="tasks")
    op.drop_table("contact_sources")
    op.drop_table("contact_addresses")
    op.drop_table("contact_phones")
    op.drop_table("contact_emails")
    op.drop_table("contacts")
    op.drop_table("task_dependencies")
    op.drop_constraint("ck_tasks_planning_state", "tasks", type_="check")
    op.drop_constraint("fk_tasks_template", "tasks", type_="foreignkey")
    op.drop_column("tasks", "planning_state")
    op.drop_column("tasks", "template_id")
    op.drop_column("tasks", "labels")
    op.drop_column("tasks", "soft_deadline")
    op.drop_column("tasks", "hard_deadline")
    op.drop_column("tasks", "latest_end")
    op.drop_column("tasks", "earliest_start")
    op.drop_column("tasks", "task_duration_min")
