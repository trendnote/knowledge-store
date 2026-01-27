#!/usr/bin/env python3
"""Initialize PostgreSQL schema for Knowledge Store.

This script creates all required tables, indexes, and constraints
for the Knowledge Store Layer.

Usage:
    python scripts/init_postgres.py           # Initialize schema
    python scripts/init_postgres.py --reset   # Drop and recreate all tables
    python scripts/init_postgres.py --verify  # Only verify existing schema

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import asyncpg
except ImportError:
    print("Error: asyncpg not installed. Run: pip install asyncpg")
    sys.exit(1)

# Load .env if exists
try:
    from dotenv import load_dotenv

    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
except ImportError:
    pass


class TableInfo(NamedTuple):
    """Table verification info."""

    name: str
    row_count: int
    index_count: int


EXPECTED_TABLES = [
    "documents",
    "document_versions",
    "document_chunks",
    "acl_entries",
    "audit_logs",
]

EXPECTED_INDEXES = [
    # documents
    "idx_documents_owner",
    "idx_documents_owner_org",
    "idx_documents_status",
    "idx_documents_security",
    "idx_documents_source",
    "idx_documents_created",
    "idx_documents_updated",
    # document_versions
    "idx_versions_doc",
    "idx_versions_doc_no",
    "idx_versions_effective",
    "idx_versions_hash",
    # document_chunks
    "idx_chunks_doc",
    "idx_chunks_version",
    "idx_chunks_milvus",
    "idx_chunks_neo4j",
    "idx_chunks_section",
    # acl_entries
    "idx_acl_doc",
    "idx_acl_principal",
    "idx_acl_permission",
    "idx_acl_expires",
    # audit_logs
    "idx_audit_user",
    "idx_audit_user_org",
    "idx_audit_timestamp",
    "idx_audit_action",
    "idx_audit_resource",
    "idx_audit_doc",
    "idx_audit_metadata",
]


async def get_connection() -> asyncpg.Connection:
    """Get PostgreSQL connection."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "knowledge_store")
    user = os.getenv("POSTGRES_USER", "ks_user")
    password = os.getenv("POSTGRES_PASSWORD", "ks_password")

    return await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        timeout=30,
    )


async def execute_sql_file(conn: asyncpg.Connection, filepath: Path) -> None:
    """Execute SQL file."""
    print(f"  Executing: {filepath.name}")
    sql = filepath.read_text(encoding="utf-8")

    # Execute as a single transaction
    async with conn.transaction():
        await conn.execute(sql)

    print("  Done")


async def get_table_info(conn: asyncpg.Connection) -> list[TableInfo]:
    """Get information about all tables."""
    tables = []

    for table_name in EXPECTED_TABLES:
        # Check if table exists and get row count
        try:
            row_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
            )
        except asyncpg.UndefinedTableError:
            row_count = -1  # Table doesn't exist

        # Get index count for this table
        index_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND tablename = $1
            AND indexname LIKE 'idx_%'
            """,
            table_name,
        )

        tables.append(
            TableInfo(
                name=table_name,
                row_count=row_count if row_count is not None else -1,
                index_count=index_count or 0,
            )
        )

    return tables


async def get_existing_indexes(conn: asyncpg.Connection) -> set[str]:
    """Get all existing indexes."""
    rows = await conn.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
        """
    )
    return {row["indexname"] for row in rows}


async def get_foreign_keys(conn: asyncpg.Connection) -> list[dict[str, str]]:
    """Get all foreign key constraints."""
    rows = await conn.fetch(
        """
        SELECT
            tc.constraint_name,
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
        ORDER BY tc.table_name
        """
    )
    return [dict(row) for row in rows]


async def verify_schema(conn: asyncpg.Connection) -> bool:
    """Verify all tables, indexes, and constraints exist."""
    all_ok = True

    # Check tables
    print("\n  Tables:")
    table_infos = await get_table_info(conn)
    for info in table_infos:
        if info.row_count >= 0:
            print(f"    {info.name}: {info.row_count} rows, {info.index_count} indexes")
        else:
            print(f"    {info.name}: NOT FOUND")
            all_ok = False

    # Check indexes
    print("\n  Indexes:")
    existing_indexes = await get_existing_indexes(conn)
    missing_indexes = set(EXPECTED_INDEXES) - existing_indexes
    extra_indexes = existing_indexes - set(EXPECTED_INDEXES)

    print(f"    Expected: {len(EXPECTED_INDEXES)}")
    print(f"    Found: {len(existing_indexes)}")

    if missing_indexes:
        print(f"    Missing: {', '.join(sorted(missing_indexes))}")
        all_ok = False

    if extra_indexes:
        print(f"    Extra: {', '.join(sorted(extra_indexes))}")

    # Check foreign keys
    print("\n  Foreign Keys:")
    fks = await get_foreign_keys(conn)
    for fk in fks:
        print(
            f"    {fk['table_name']}.{fk['column_name']} -> "
            f"{fk['foreign_table_name']}.{fk['foreign_column_name']}"
        )

    if len(fks) < 4:  # Expected: 4 FKs
        print("    Warning: Expected at least 4 foreign keys")
        all_ok = False

    # Check triggers
    print("\n  Triggers:")
    triggers = await conn.fetch(
        """
        SELECT trigger_name, event_object_table, action_timing, event_manipulation
        FROM information_schema.triggers
        WHERE trigger_schema = 'public'
        """
    )
    for t in triggers:
        print(
            f"    {t['trigger_name']} ON {t['event_object_table']} "
            f"({t['action_timing']} {t['event_manipulation']})"
        )

    return all_ok


async def reset_schema(conn: asyncpg.Connection) -> None:
    """Drop all tables and recreate schema."""
    print("\n  Dropping existing tables...")

    # Drop in reverse order to handle foreign keys
    tables_to_drop = [
        "audit_logs",
        "acl_entries",
        "document_chunks",
        "document_versions",
        "documents",
    ]

    async with conn.transaction():
        for table in tables_to_drop:
            await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")  # noqa: S608
            print(f"    Dropped: {table}")

    print("  All tables dropped")


async def main(reset: bool = False, verify_only: bool = False) -> int:
    """Main function."""
    print("\n" + "=" * 60)
    print("  PostgreSQL Schema Initialization")
    print("=" * 60)

    # Connection info
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "knowledge_store")
    print(f"\n  Target: {host}:{port}/{database}")

    try:
        conn = await get_connection()
        print("  Connection: OK")
    except asyncpg.InvalidCatalogNameError:
        print(f"\n  Database '{database}' does not exist.")
        print("  Please create it first or check your configuration.")
        return 1
    except asyncpg.InvalidPasswordError:
        print("\n  Authentication failed. Check username/password.")
        return 1
    except OSError as e:
        print(f"\n  Connection failed: {e}")
        return 1

    try:
        # Verify only mode
        if verify_only:
            print("\n  Mode: Verify Only")
            print("-" * 60)
            ok = await verify_schema(conn)
            print("-" * 60)
            if ok:
                print("\n  Schema verification: PASSED")
                return 0
            else:
                print("\n  Schema verification: FAILED")
                return 1

        # Reset mode
        if reset:
            print("\n  Mode: Reset (DROP + CREATE)")
            print("-" * 60)
            await reset_schema(conn)
        else:
            print("\n  Mode: Initialize (CREATE IF NOT EXISTS)")

        # Execute SQL files
        print("-" * 60)
        print("\n  Executing SQL files:")
        sql_dir = Path(__file__).parent / "sql"
        sql_files = sorted(sql_dir.glob("*.sql"))

        if not sql_files:
            print("  No SQL files found in scripts/sql/")
            return 1

        for sql_file in sql_files:
            await execute_sql_file(conn, sql_file)

        # Verify
        print("-" * 60)
        print("\n  Verifying schema:")
        all_ok = await verify_schema(conn)

        print("-" * 60)
        if all_ok:
            print("\n  Schema initialization: SUCCESS")
            return 0
        else:
            print("\n  Schema initialization: INCOMPLETE")
            return 1

    except asyncpg.PostgresSyntaxError as e:
        print(f"\n  SQL Syntax Error: {e}")
        return 1
    except asyncpg.PostgresError as e:
        print(f"\n  PostgreSQL Error: {e}")
        return 1
    except Exception as e:
        print(f"\n  Error: {e}")
        return 1
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL schema for Knowledge Store"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables and recreate schema (WARNING: Data loss!)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing schema without changes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.reset:
        print("\n  WARNING: This will DELETE ALL DATA in the database!")
        print("  Press Ctrl+C to cancel, or wait 3 seconds to continue...")
        try:
            import time

            time.sleep(3)
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            sys.exit(0)

    try:
        exit_code = asyncio.run(main(reset=args.reset, verify_only=args.verify))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user")
        sys.exit(130)
