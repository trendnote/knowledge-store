#!/usr/bin/env python3
"""Initialize all database schemas for Knowledge Store.

This script initializes all database schemas in order:
1. PostgreSQL (metadata store)
2. Milvus (vector store)
3. Neo4j (graph store)

Usage:
    python scripts/init_all.py              # Initialize all (skip existing)
    python scripts/init_all.py --reset      # Reset and reinitialize all
    python scripts/init_all.py --check      # Check connection status only
    python scripts/init_all.py --postgres-only  # PostgreSQL only
    python scripts/init_all.py --milvus-only    # Milvus only
    python scripts/init_all.py --neo4j-only     # Neo4j only

Environment Variables:
    See .env file for database connection settings.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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


class Status(Enum):
    """Initialization status."""

    SUCCESS = "✅"
    SKIPPED = "⏭️"
    FAILED = "❌"
    PENDING = "⏳"


@dataclass
class InitResult:
    """Result of initialization."""

    name: str
    status: Status
    message: str
    duration_seconds: float = 0.0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize all Knowledge Store schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/init_all.py              # Initialize all (skip existing)
  python scripts/init_all.py --reset      # Reset and reinitialize all
  python scripts/init_all.py --postgres-only  # PostgreSQL only
  python scripts/init_all.py --check      # Check status only
        """,
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing schemas and recreate (WARNING: Data loss!)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check connection status only (no changes)",
    )
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help="Initialize PostgreSQL only",
    )
    parser.add_argument(
        "--milvus-only",
        action="store_true",
        help="Initialize Milvus only",
    )
    parser.add_argument(
        "--neo4j-only",
        action="store_true",
        help="Initialize Neo4j only",
    )

    return parser.parse_args()


def init_postgres(reset: bool = False) -> InitResult:
    """Initialize PostgreSQL schema."""
    start_time = time.time()
    name = "PostgreSQL"

    try:
        script_path = Path(__file__).parent / "init_postgres.py"
        if not script_path.exists():
            return InitResult(name, Status.FAILED, "Script not found", 0.0)

        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Schema initialized", duration)
        else:
            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
            return InitResult(name, Status.FAILED, error_msg.strip(), duration)
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, "Timeout (120s)", duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:200], duration)


def init_milvus(reset: bool = False) -> InitResult:
    """Initialize Milvus collection."""
    start_time = time.time()
    name = "Milvus"

    try:
        script_path = Path(__file__).parent / "init_milvus.py"
        if not script_path.exists():
            return InitResult(name, Status.FAILED, "Script not found", 0.0)

        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Collection initialized", duration)
        else:
            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
            return InitResult(name, Status.FAILED, error_msg.strip(), duration)
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, "Timeout (120s)", duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:200], duration)


def init_neo4j(reset: bool = False) -> InitResult:
    """Initialize Neo4j schema."""
    start_time = time.time()
    name = "Neo4j"

    try:
        script_path = Path(__file__).parent / "init_neo4j.py"
        if not script_path.exists():
            return InitResult(name, Status.FAILED, "Script not found", 0.0)

        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        # Neo4j reset has 3 second warning delay
        timeout = 130 if reset else 120

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Constraints/Indexes created", duration)
        else:
            error_msg = result.stderr[:200] if result.stderr else result.stdout[:200]
            return InitResult(name, Status.FAILED, error_msg.strip(), duration)
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, "Timeout", duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:200], duration)


async def check_postgres() -> InitResult:
    """Check PostgreSQL connection."""
    name = "PostgreSQL"
    start_time = time.time()

    try:
        import asyncpg

        conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5433")),
            database=os.getenv("POSTGRES_DB", "knowledge_store"),
            user=os.getenv("POSTGRES_USER", "ks_user"),
            password=os.getenv("POSTGRES_PASSWORD", "ks_password"),
            timeout=10,
        )

        # Check if tables exist
        tables = await conn.fetch(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        await conn.close()

        duration = time.time() - start_time
        table_count = len(tables)
        return InitResult(
            name,
            Status.SUCCESS,
            f"Connected ({table_count} tables)",
            duration,
        )
    except ImportError:
        return InitResult(name, Status.FAILED, "asyncpg not installed", 0.0)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:100], duration)


async def check_milvus() -> InitResult:
    """Check Milvus connection."""
    name = "Milvus"
    start_time = time.time()

    try:
        from pymilvus import connections, utility

        connections.connect(
            alias="check",
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=os.getenv("MILVUS_PORT", "19531"),
            timeout=10,
        )

        # Check collections
        collections = utility.list_collections(using="check")

        connections.disconnect("check")

        duration = time.time() - start_time
        collection_count = len(collections)
        return InitResult(
            name,
            Status.SUCCESS,
            f"Connected ({collection_count} collections)",
            duration,
        )
    except ImportError:
        return InitResult(name, Status.FAILED, "pymilvus not installed", 0.0)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:100], duration)


async def check_neo4j() -> InitResult:
    """Check Neo4j connection."""
    name = "Neo4j"
    start_time = time.time()

    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "neo4j_password"),
            ),
        )
        await driver.verify_connectivity()

        # Check constraints
        async with driver.session() as session:
            result = await session.run("SHOW CONSTRAINTS")
            constraints = [r async for r in result]

        await driver.close()

        duration = time.time() - start_time
        constraint_count = len(constraints)
        return InitResult(
            name,
            Status.SUCCESS,
            f"Connected ({constraint_count} constraints)",
            duration,
        )
    except ImportError:
        return InitResult(name, Status.FAILED, "neo4j not installed", 0.0)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e)[:100], duration)


async def check_connections() -> list[InitResult]:
    """Check all connections without making changes."""
    results = await asyncio.gather(
        check_postgres(),
        check_milvus(),
        check_neo4j(),
    )
    return list(results)


def print_results(results: list[InitResult]) -> None:
    """Print results summary table."""
    print("\n" + "=" * 65)
    print("                   INITIALIZATION SUMMARY")
    print("=" * 65 + "\n")

    # Table header
    print(f"  {'Component':<12} {'Status':<8} {'Duration':<10} {'Message'}")
    print("  " + "-" * 61)

    # Table rows
    for r in results:
        duration_str = f"{r.duration_seconds:.1f}s" if r.duration_seconds > 0 else "-"
        status_str = r.status.value
        message = r.message[:38] + "..." if len(r.message) > 38 else r.message
        print(f"  {r.name:<12} {status_str:<8} {duration_str:<10} {message}")

    print("  " + "-" * 61)

    # Summary
    success_count = sum(1 for r in results if r.status == Status.SUCCESS)
    failed_count = sum(1 for r in results if r.status == Status.FAILED)
    skipped_count = sum(1 for r in results if r.status == Status.SKIPPED)
    total_time = sum(r.duration_seconds for r in results)

    parts = []
    if success_count > 0:
        parts.append(f"{success_count} succeeded")
    if failed_count > 0:
        parts.append(f"{failed_count} failed")
    if skipped_count > 0:
        parts.append(f"{skipped_count} skipped")

    print(f"\n  Total: {', '.join(parts)}")
    print(f"  Time: {total_time:.1f}s")

    if failed_count == 0:
        print("\n  ✅ All initializations completed successfully!")
    else:
        print(f"\n  ❌ {failed_count} initialization(s) failed")


async def main() -> int:
    """Main function."""
    args = parse_args()

    print("\n" + "=" * 65)
    print("        KNOWLEDGE STORE - SCHEMA INITIALIZATION")
    print("=" * 65)

    # Check mode
    if args.check:
        print("\n  Mode: Connection Check (no changes)")
        print("-" * 65)
        print("\n  🔍 Checking connections...\n")
        results = await check_connections()
        print_results(results)
        failed = any(r.status == Status.FAILED for r in results)
        return 1 if failed else 0

    # Determine which to initialize
    only_mode = args.postgres_only or args.milvus_only or args.neo4j_only
    init_postgres_flag = args.postgres_only or not only_mode
    init_milvus_flag = args.milvus_only or not only_mode
    init_neo4j_flag = args.neo4j_only or not only_mode

    # Mode display
    if args.reset:
        print("\n  Mode: Reset (DROP + CREATE)")
        print("  ⚠️  WARNING: Existing data will be deleted!")
    else:
        print("\n  Mode: Initialize (CREATE IF NOT EXISTS)")

    print("-" * 65)

    results: list[InitResult] = []
    step = 0
    total_steps = sum([init_postgres_flag, init_milvus_flag, init_neo4j_flag])

    # Initialize in order
    if init_postgres_flag:
        step += 1
        print(f"\n  📦 [{step}/{total_steps}] Initializing PostgreSQL...")
        result = init_postgres(reset=args.reset)
        results.append(result)
        print(f"     {result.status.value} {result.message}")

    if init_milvus_flag:
        step += 1
        print(f"\n  📦 [{step}/{total_steps}] Initializing Milvus...")
        result = init_milvus(reset=args.reset)
        results.append(result)
        print(f"     {result.status.value} {result.message}")

    if init_neo4j_flag:
        step += 1
        print(f"\n  📦 [{step}/{total_steps}] Initializing Neo4j...")
        result = init_neo4j(reset=args.reset)
        results.append(result)
        print(f"     {result.status.value} {result.message}")

    # Print summary
    print_results(results)

    # Return exit code
    failed = any(r.status == Status.FAILED for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user")
        sys.exit(130)
