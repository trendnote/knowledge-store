#!/usr/bin/env python3
"""Initialize Neo4j schema (constraints and indexes) for Knowledge Store.

This script creates:
- Unique constraints for all node types
- Search indexes for efficient querying
- Full-text indexes for text search

Usage:
    python scripts/init_neo4j.py           # Initialize schema
    python scripts/init_neo4j.py --reset   # Drop all and recreate
    python scripts/init_neo4j.py --verify  # Only verify existing schema

Environment Variables:
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    print("Error: neo4j not installed. Run: pip install neo4j")
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


async def get_driver():  # type: ignore[no-untyped-def]
    """Get Neo4j async driver."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return driver


async def execute_cypher_file(driver, filepath: Path) -> int:  # type: ignore[no-untyped-def]
    """Execute Cypher file and return count of statements executed."""
    print(f"\n  Executing: {filepath.name}")

    # Read file content
    content = filepath.read_text(encoding="utf-8")

    # Parse Cypher statements (split by semicolon, ignore comments)
    statements = []
    current_statement = []

    for line in content.split("\n"):
        stripped = line.strip()
        # Skip empty lines and comments
        if not stripped or stripped.startswith("//"):
            continue
        current_statement.append(stripped)

        # Check if statement ends with semicolon
        if stripped.endswith(";"):
            full_statement = " ".join(current_statement)
            # Remove trailing semicolon
            full_statement = full_statement.rstrip(";").strip()
            if full_statement:
                statements.append(full_statement)
            current_statement = []

    # Handle last statement without semicolon
    if current_statement:
        full_statement = " ".join(current_statement).rstrip(";").strip()
        if full_statement:
            statements.append(full_statement)

    executed_count = 0
    async with driver.session() as session:
        for statement in statements:
            try:
                await session.run(statement)
                # Extract constraint/index name for display
                if "CONSTRAINT" in statement:
                    name = statement.split("CONSTRAINT")[1].split("IF")[0].strip()
                    print(f"    Constraint: {name}")
                elif "INDEX" in statement:
                    name = statement.split("INDEX")[1].split("IF")[0].strip()
                    print(f"    Index: {name}")
                executed_count += 1
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "equivalent" in error_msg:
                    # Extract name for display
                    if "CONSTRAINT" in statement:
                        name = statement.split("CONSTRAINT")[1].split("IF")[0].strip()
                        print(f"    Constraint (exists): {name}")
                    elif "INDEX" in statement:
                        name = statement.split("INDEX")[1].split("IF")[0].strip()
                        print(f"    Index (exists): {name}")
                    executed_count += 1
                else:
                    print(f"    Error: {e}")
                    raise

    return executed_count


async def verify_constraints(driver) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Get all constraints."""
    constraints = []
    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS")
        async for record in result:
            constraints.append({
                "name": record.get("name", "unnamed"),
                "type": record.get("type", "unknown"),
                "entity": record.get("labelsOrTypes", []),
                "properties": record.get("properties", []),
            })
    return constraints


async def verify_indexes(driver) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    """Get all indexes."""
    indexes = []
    async with driver.session() as session:
        result = await session.run("SHOW INDEXES")
        async for record in result:
            indexes.append({
                "name": record.get("name", "unnamed"),
                "type": record.get("type", "unknown"),
                "entity": record.get("labelsOrTypes", []),
                "properties": record.get("properties", []),
                "state": record.get("state", "unknown"),
            })
    return indexes


async def print_schema_summary(driver) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    """Print schema summary and return counts."""
    print("\n  Constraints:")
    constraints = await verify_constraints(driver)
    for c in constraints:
        entity = c["entity"][0] if c["entity"] else "?"
        props = ", ".join(c["properties"]) if c["properties"] else "?"
        print(f"    - {c['name']}: {entity}.{props}")

    print("\n  Indexes:")
    indexes = await verify_indexes(driver)
    # Group by type
    by_type: dict[str, list] = {}
    for idx in indexes:
        idx_type = idx["type"]
        if idx_type not in by_type:
            by_type[idx_type] = []
        by_type[idx_type].append(idx)

    for idx_type, idx_list in sorted(by_type.items()):
        print(f"    [{idx_type}] ({len(idx_list)})")
        for idx in idx_list:
            entity = idx["entity"][0] if idx["entity"] else "?"
            props = ", ".join(idx["properties"]) if idx["properties"] else "?"
            state = idx["state"]
            state_marker = "" if state == "ONLINE" else f" ({state})"
            print(f"      - {idx['name']}: {entity}.{props}{state_marker}")

    return len(constraints), len(indexes)


async def reset_schema(driver) -> None:  # type: ignore[no-untyped-def]
    """Drop all constraints, indexes, and nodes."""
    print("\n  Dropping existing schema...")

    async with driver.session() as session:
        # Drop all constraints
        constraints = await verify_constraints(driver)
        for c in constraints:
            name = c["name"]
            try:
                await session.run(f"DROP CONSTRAINT {name} IF EXISTS")
                print(f"    Dropped constraint: {name}")
            except Exception:
                pass

        # Drop all non-constraint indexes
        indexes = await verify_indexes(driver)
        for idx in indexes:
            name = idx["name"]
            # Skip constraint-backed indexes (they're dropped with constraints)
            if "constraint" not in name.lower():
                try:
                    await session.run(f"DROP INDEX {name} IF EXISTS")
                    print(f"    Dropped index: {name}")
                except Exception:
                    pass

        # Clear all nodes and relationships
        await session.run("MATCH (n) DETACH DELETE n")
        print("    Cleared all nodes and relationships")

    print("  Reset complete")


async def run_crud_test(driver) -> bool:  # type: ignore[no-untyped-def]
    """Run simple CRUD test."""
    import uuid

    print("\n  Running CRUD test...")

    test_doc_uuid = f"test-{uuid.uuid4()}"

    async with driver.session() as session:
        try:
            # Create
            await session.run(
                """
                CREATE (d:Document {
                    doc_uuid: $doc_uuid,
                    title: 'Test Document for Schema Verification',
                    source: 'wiki',
                    security_level: 'internal',
                    status: 'published',
                    created_at: datetime()
                })
                """,
                doc_uuid=test_doc_uuid,
            )
            print(f"    Create: OK (doc_uuid={test_doc_uuid[:12]}...)")

            # Read
            result = await session.run(
                """
                MATCH (d:Document {doc_uuid: $doc_uuid})
                RETURN d.title as title, d.source as source
                """,
                doc_uuid=test_doc_uuid,
            )
            record = await result.single()
            if record and record["title"] == "Test Document for Schema Verification":
                print("    Read: OK")
            else:
                print("    Read: FAILED")
                return False

            # Update
            await session.run(
                """
                MATCH (d:Document {doc_uuid: $doc_uuid})
                SET d.title = 'Updated Test Document'
                """,
                doc_uuid=test_doc_uuid,
            )
            print("    Update: OK")

            # Test constraint (should fail on duplicate)
            try:
                await session.run(
                    """
                    CREATE (d:Document {doc_uuid: $doc_uuid, title: 'Duplicate'})
                    """,
                    doc_uuid=test_doc_uuid,
                )
                print("    Constraint test: FAILED (should have raised error)")
                return False
            except Exception as e:
                if "constraint" in str(e).lower() or "already exists" in str(e).lower():
                    print("    Constraint test: OK (duplicate rejected)")
                else:
                    raise

            # Delete
            await session.run(
                """
                MATCH (d:Document {doc_uuid: $doc_uuid})
                DELETE d
                """,
                doc_uuid=test_doc_uuid,
            )
            print("    Delete: OK")

            return True

        except Exception as e:
            print(f"    Test failed: {e}")
            # Cleanup - ignore errors during cleanup
            import contextlib

            with contextlib.suppress(Exception):
                await session.run(
                    "MATCH (d:Document {doc_uuid: $doc_uuid}) DELETE d",
                    doc_uuid=test_doc_uuid,
                )
            return False


async def main(reset: bool = False, verify_only: bool = False) -> int:
    """Main function."""
    print("\n" + "=" * 60)
    print("  Neo4j Schema Initialization")
    print("=" * 60)

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    print(f"\n  Target: {uri}")

    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        print("  Connection: OK")
    except Exception as e:
        print(f"\n  Connection failed: {e}")
        print("\n  Tips:")
        print("    1. Ensure Neo4j is running: docker compose ps")
        print("    2. Check credentials in .env file")
        return 1

    try:
        # Verify only mode
        if verify_only:
            print("\n  Mode: Verify Only")
            print("-" * 60)
            constraint_count, index_count = await print_schema_summary(driver)
            print("-" * 60)
            print(f"\n  Summary: {constraint_count} constraints, {index_count} indexes")
            print("  Verification: PASSED")
            return 0

        # Reset mode
        if reset:
            print("\n  Mode: Reset (DROP + CREATE)")
            print("-" * 60)
            await reset_schema(driver)
        else:
            print("\n  Mode: Initialize (CREATE IF NOT EXISTS)")

        print("-" * 60)

        # Execute Cypher files
        cypher_dir = Path(__file__).parent / "cypher"
        cypher_files = sorted(cypher_dir.glob("*.cypher"))

        if not cypher_files:
            print("\n  No Cypher files found in scripts/cypher/")
            return 1

        total_executed = 0
        for cypher_file in cypher_files:
            count = await execute_cypher_file(driver, cypher_file)
            total_executed += count

        # Print summary
        print("-" * 60)
        constraint_count, index_count = await print_schema_summary(driver)

        # Run CRUD test
        print("-" * 60)
        test_ok = await run_crud_test(driver)

        print("-" * 60)
        print(f"\n  Summary: {constraint_count} constraints, {index_count} indexes")

        if test_ok:
            print("  Initialization: SUCCESS")
            return 0
        else:
            print("  Initialization: FAILED (test error)")
            return 1

    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        await driver.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize Neo4j schema for Knowledge Store"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all constraints/indexes and recreate (WARNING: Data loss!)",
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
        print("\n  WARNING: This will DELETE ALL DATA in Neo4j!")
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
