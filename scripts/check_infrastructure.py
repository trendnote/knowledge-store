#!/usr/bin/env python3
"""Infrastructure connectivity check script.

This script tests connections to all required infrastructure components:
- PostgreSQL (metadata, ACL, audit)
- Milvus (vector database)
- Neo4j (graph database)
- Kafka (event streaming)

Usage:
    python scripts/check_infrastructure.py

Environment Variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    MILVUS_HOST, MILVUS_PORT
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    KAFKA_BOOTSTRAP_SERVERS

Exit Codes:
    0: All connections successful
    1: One or more connections failed
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import NamedTuple

# Load .env from project root if exists
try:
    from dotenv import load_dotenv

    # Try to load from project root
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
except ImportError:
    pass


class ConnectionResult(NamedTuple):
    """Connection test result."""

    name: str
    success: bool
    message: str
    details: str = ""


def print_result(result: ConnectionResult) -> None:
    """Print connection result with emoji."""
    emoji = "✅" if result.success else "❌"
    print(f"{emoji} {result.name}: {result.message}")
    if result.details and not result.success:
        print(f"   └─ {result.details}")


async def check_postgres() -> ConnectionResult:
    """Check PostgreSQL connection using asyncpg."""
    try:
        import asyncpg
    except ImportError:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message="asyncpg not installed",
            details="Run: pip install asyncpg",
        )

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "knowledge_store")
    user = os.getenv("POSTGRES_USER", "ks_user")
    password = os.getenv("POSTGRES_PASSWORD", "ks_password")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=10,
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()

        # Extract short version info
        version_short = version.split(",")[0] if version else "Unknown"

        return ConnectionResult(
            name="PostgreSQL",
            success=True,
            message=f"Connected to {host}:{port}/{database}",
            details=version_short,
        )
    except asyncpg.InvalidCatalogNameError:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message=f"Database '{database}' does not exist",
            details=f"Host: {host}:{port}",
        )
    except asyncpg.InvalidPasswordError:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message="Invalid username or password",
            details=f"User: {user}@{host}:{port}",
        )
    except OSError as e:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message="Connection refused",
            details=f"{host}:{port} - {e}",
        )
    except Exception as e:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message="Connection failed",
            details=str(e),
        )


async def check_milvus() -> ConnectionResult:
    """Check Milvus connection using pymilvus."""
    try:
        from pymilvus import MilvusClient
    except ImportError:
        return ConnectionResult(
            name="Milvus",
            success=False,
            message="pymilvus not installed",
            details="Run: pip install pymilvus",
        )

    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")
    uri = f"http://{host}:{port}"

    try:
        # Use MilvusClient for simpler connection handling
        loop = asyncio.get_event_loop()

        def connect_and_check() -> str:
            client = MilvusClient(uri=uri, timeout=10)
            # List collections to verify connection
            collections = client.list_collections()
            client.close()
            return f"{len(collections)} collection(s)"

        result = await loop.run_in_executor(None, connect_and_check)

        return ConnectionResult(
            name="Milvus",
            success=True,
            message=f"Connected to {host}:{port}",
            details=result,
        )
    except Exception as e:
        error_msg = str(e)
        if "connection refused" in error_msg.lower():
            return ConnectionResult(
                name="Milvus",
                success=False,
                message="Connection refused",
                details=f"{host}:{port}",
            )
        return ConnectionResult(
            name="Milvus",
            success=False,
            message="Connection failed",
            details=error_msg[:100],
        )


async def check_neo4j() -> ConnectionResult:
    """Check Neo4j connection using neo4j driver."""
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        return ConnectionResult(
            name="Neo4j",
            success=False,
            message="neo4j not installed",
            details="Run: pip install neo4j",
        )

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")

    driver = None
    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await driver.verify_connectivity()

        # Get server info
        async with driver.session() as session:
            result = await session.run(
                "CALL dbms.components() YIELD name, versions RETURN name, versions[0] as version"
            )
            record = await result.single()
            server_info = (
                f"{record['name']} v{record['version']}" if record else "Connected"
            )

        return ConnectionResult(
            name="Neo4j",
            success=True,
            message=f"Connected to {uri}",
            details=server_info,
        )
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower():
            return ConnectionResult(
                name="Neo4j",
                success=False,
                message="Authentication failed",
                details=f"User: {user}",
            )
        if "connection refused" in error_msg.lower() or "unable to retrieve" in error_msg.lower():
            return ConnectionResult(
                name="Neo4j",
                success=False,
                message="Connection refused",
                details=uri,
            )
        return ConnectionResult(
            name="Neo4j",
            success=False,
            message="Connection failed",
            details=error_msg[:100],
        )
    finally:
        if driver:
            await driver.close()


async def check_kafka() -> ConnectionResult:
    """Check Kafka connection using aiokafka."""
    try:
        from aiokafka import AIOKafkaProducer
        from aiokafka.errors import KafkaConnectionError
    except ImportError:
        return ConnectionResult(
            name="Kafka",
            success=False,
            message="aiokafka not installed",
            details="Run: pip install aiokafka",
        )

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    producer = None
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            request_timeout_ms=10000,
            metadata_max_age_ms=5000,
        )
        await producer.start()

        # Get cluster metadata
        partitions = producer.client.cluster.topics()
        topic_count = len([t for t in partitions if not t.startswith("_")])

        return ConnectionResult(
            name="Kafka",
            success=True,
            message=f"Connected to {bootstrap_servers}",
            details=f"{topic_count} topic(s)",
        )
    except KafkaConnectionError:
        return ConnectionResult(
            name="Kafka",
            success=False,
            message="Connection refused",
            details=bootstrap_servers,
        )
    except Exception as e:
        error_msg = str(e)
        if "NoBrokersAvailable" in error_msg or "connection refused" in error_msg.lower():
            return ConnectionResult(
                name="Kafka",
                success=False,
                message="No brokers available",
                details=bootstrap_servers,
            )
        return ConnectionResult(
            name="Kafka",
            success=False,
            message="Connection failed",
            details=error_msg[:100],
        )
    finally:
        if producer:
            await producer.stop()


async def main() -> int:
    """Run all connection tests and return exit code."""
    print("\n" + "=" * 50)
    print("  Infrastructure Connection Check")
    print("=" * 50 + "\n")

    # Run all connection tests concurrently
    results = await asyncio.gather(
        check_postgres(),
        check_milvus(),
        check_neo4j(),
        check_kafka(),
    )

    # Print results
    for result in results:
        print_result(result)

    # Summary
    failed = [r for r in results if not r.success]

    print("\n" + "-" * 50)

    if failed:
        print(f"\n❌ {len(failed)}/{len(results)} connection(s) failed:")
        for r in failed:
            print(f"   - {r.name}")
        print("\nTips:")
        print("  1. Ensure Docker services are running: docker compose ps")
        print("  2. Check .env file for correct connection settings")
        print("  3. View logs: docker compose logs [service]")
        return 1
    else:
        print(f"\n✅ All {len(results)} connections OK!")
        return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
