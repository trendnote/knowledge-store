#!/usr/bin/env python3
"""Initialize Milvus collection for Knowledge Store.

This script creates the knowledge_chunks collection with:
- Dense embeddings (BGE-M3 1024d)
- Sparse embeddings (BM25)
- Metadata fields for filtering
- HNSW and SPARSE_INVERTED_INDEX indexes

Usage:
    python scripts/init_milvus.py           # Initialize collection
    python scripts/init_milvus.py --reset   # Drop and recreate collection
    python scripts/init_milvus.py --verify  # Only verify existing collection

Environment Variables:
    MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        connections,
        utility,
    )
except ImportError:
    print("Error: pymilvus not installed. Run: pip install pymilvus")
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

# Configuration
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "knowledge_chunks")
DENSE_DIM = 1024  # BGE-M3 dense embedding dimension


def get_collection_schema() -> CollectionSchema:
    """Define collection schema for knowledge chunks."""
    fields = [
        # Primary Key - Chunk UUID
        FieldSchema(
            name="chunk_uuid",
            dtype=DataType.VARCHAR,
            max_length=36,
            is_primary=True,
            auto_id=False,
            description="Chunk unique identifier (UUID)",
        ),
        # Document reference
        FieldSchema(
            name="doc_uuid",
            dtype=DataType.VARCHAR,
            max_length=36,
            description="Document unique identifier",
        ),
        # Version reference
        FieldSchema(
            name="version_id",
            dtype=DataType.VARCHAR,
            max_length=36,
            description="Document version identifier",
        ),
        # Dense embedding (BGE-M3)
        FieldSchema(
            name="dense_embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=DENSE_DIM,
            description="BGE-M3 dense embedding (1024d)",
        ),
        # Sparse embedding (BM25)
        FieldSchema(
            name="sparse_embedding",
            dtype=DataType.SPARSE_FLOAT_VECTOR,
            description="BGE-M3 sparse embedding (BM25)",
        ),
        # Chunk text
        FieldSchema(
            name="chunk_text",
            dtype=DataType.VARCHAR,
            max_length=16000,
            description="Chunk text content",
        ),
        # Section path
        FieldSchema(
            name="section_path",
            dtype=DataType.VARCHAR,
            max_length=500,
            description="Section path in document",
        ),
        # Chunk number
        FieldSchema(
            name="chunk_no",
            dtype=DataType.INT64,
            description="Chunk sequence number within document",
        ),
        # Security level for ACL filtering
        FieldSchema(
            name="security_level",
            dtype=DataType.VARCHAR,
            max_length=20,
            description="Security level (public/internal/confidential)",
        ),
        # Owner organization for filtering
        FieldSchema(
            name="owner_org",
            dtype=DataType.VARCHAR,
            max_length=100,
            description="Owner organization",
        ),
        # Allowed groups (for ACL filtering)
        FieldSchema(
            name="allowed_groups",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_length=100,
            max_capacity=50,
            description="List of allowed groups for ACL",
        ),
        # Created timestamp
        FieldSchema(
            name="created_at",
            dtype=DataType.INT64,
            description="Creation timestamp (Unix)",
        ),
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Knowledge Store Chunks - Hybrid Search Collection with BGE-M3",
        enable_dynamic_field=False,
    )

    return schema


def create_indexes(collection: Collection) -> None:
    """Create indexes for the collection."""
    print("\n  Creating indexes...")

    # Dense embedding index (HNSW with COSINE)
    print("    HNSW index for dense_embedding...")
    dense_index_params = {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {
            "M": 16,  # Max edges per node
            "efConstruction": 256,  # Construction time accuracy
        },
    }
    collection.create_index(
        field_name="dense_embedding",
        index_params=dense_index_params,
        index_name="idx_dense_hnsw",
    )
    print("    Done")

    # Sparse embedding index (SPARSE_INVERTED_INDEX)
    print("    SPARSE_INVERTED_INDEX for sparse_embedding...")
    sparse_index_params = {
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "IP",  # Inner Product for sparse vectors
        "params": {
            "drop_ratio_build": 0.2,  # Drop low-value terms during build
        },
    }
    collection.create_index(
        field_name="sparse_embedding",
        index_params=sparse_index_params,
        index_name="idx_sparse_inverted",
    )
    print("    Done")

    # Scalar indexes for filtering
    print("    Scalar indexes...")
    collection.create_index(
        field_name="doc_uuid",
        index_name="idx_doc_uuid",
    )
    collection.create_index(
        field_name="security_level",
        index_name="idx_security_level",
    )
    collection.create_index(
        field_name="owner_org",
        index_name="idx_owner_org",
    )
    print("    Done")

    print("  All indexes created")


def connect_milvus() -> None:
    """Connect to Milvus server."""
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")

    print(f"\n  Target: {host}:{port}")
    connections.connect(
        alias="default",
        host=host,
        port=port,
        timeout=30,
    )
    print("  Connection: OK")


def create_collection(reset: bool = False) -> Collection:
    """Create or get collection."""
    # Check if collection exists
    if utility.has_collection(COLLECTION_NAME):
        if reset:
            print(f"\n  Dropping existing collection: {COLLECTION_NAME}")
            utility.drop_collection(COLLECTION_NAME)
            print("  Collection dropped")
        else:
            print(f"\n  Collection exists: {COLLECTION_NAME}")
            return Collection(COLLECTION_NAME)

    # Create new collection
    print(f"\n  Creating collection: {COLLECTION_NAME}")
    schema = get_collection_schema()
    collection = Collection(
        name=COLLECTION_NAME,
        schema=schema,
        using="default",
    )
    print("  Collection created")

    return collection


def verify_collection(collection: Collection) -> bool:
    """Verify collection setup."""
    print("\n  Verification:")

    # Check schema
    schema = collection.schema
    print(f"    Fields: {len(schema.fields)}")
    for field in schema.fields:
        pk_marker = " (PK)" if field.is_primary else ""
        dtype_name = field.dtype.name
        if dtype_name == "FLOAT_VECTOR":
            dtype_name = f"FLOAT_VECTOR[{field.params.get('dim', '?')}]"
        print(f"      - {field.name}: {dtype_name}{pk_marker}")

    # Check indexes
    indexes = collection.indexes
    print(f"    Indexes: {len(indexes)}")
    for idx in indexes:
        idx_type = idx.params.get("index_type", "SCALAR")
        metric = idx.params.get("metric_type", "")
        metric_str = f" ({metric})" if metric else ""
        print(f"      - {idx.field_name}: {idx_type}{metric_str}")

    # Load collection
    print("\n  Loading collection into memory...")
    collection.load()
    print("  Collection loaded")

    # Get stats
    stats = collection.num_entities
    print(f"  Entities: {stats}")

    return True


def run_insert_search_test(collection: Collection) -> bool:
    """Test insert, search, and delete operations."""
    import uuid

    from scipy.sparse import csr_array

    print("\n  Running functional test...")

    test_uuid = str(uuid.uuid4())
    test_doc_uuid = str(uuid.uuid4())
    test_version_id = str(uuid.uuid4())

    # Create sparse vector using scipy (Milvus expected format)
    # Simulate a sparse vector with some non-zero values at specific indices
    sparse_indices = [100, 200, 300]
    sparse_values = [0.5, 0.3, 0.2]
    sparse_vector = csr_array(
        (sparse_values, ([0] * len(sparse_indices), sparse_indices)),
        shape=(1, 30000),
    )

    # Prepare test data as list of rows
    test_data = [
        {
            "chunk_uuid": test_uuid,
            "doc_uuid": test_doc_uuid,
            "version_id": test_version_id,
            "dense_embedding": [0.1] * DENSE_DIM,
            "sparse_embedding": sparse_vector,
            "chunk_text": "This is a test chunk for Knowledge Store verification.",
            "section_path": "/test/section/1",
            "chunk_no": 1,
            "security_level": "internal",
            "owner_org": "test-org",
            "allowed_groups": ["group1", "group2"],
            "created_at": int(time.time()),
        }
    ]

    try:
        # Insert
        collection.insert(test_data)
        collection.flush()
        print(f"    Insert: OK (chunk_uuid={test_uuid[:8]}...)")

        # Dense search
        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 64},
        }
        results = collection.search(
            data=[[0.1] * DENSE_DIM],
            anns_field="dense_embedding",
            param=search_params,
            limit=1,
            output_fields=["chunk_uuid", "chunk_text"],
        )
        if results and len(results[0]) > 0:
            print(f"    Dense Search: OK (found {len(results[0])} result)")
        else:
            print("    Dense Search: No results")
            return False

        # Hybrid search test
        from pymilvus import AnnSearchRequest, RRFRanker

        dense_req = AnnSearchRequest(
            data=[[0.1] * DENSE_DIM],
            anns_field="dense_embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=5,
        )

        # Create sparse search vector
        search_sparse = csr_array(
            ([0.5, 0.3], ([0, 0], [100, 200])),
            shape=(1, 30000),
        )
        sparse_req = AnnSearchRequest(
            data=[search_sparse],
            anns_field="sparse_embedding",
            param={"metric_type": "IP"},
            limit=5,
        )

        hybrid_results = collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            rerank=RRFRanker(k=60),
            limit=5,
            output_fields=["chunk_uuid", "chunk_text"],
        )
        if hybrid_results and len(hybrid_results[0]) > 0:
            print(f"    Hybrid Search: OK (found {len(hybrid_results[0])} result)")
        else:
            print("    Hybrid Search: No results")

        # Delete
        collection.delete(f'chunk_uuid == "{test_uuid}"')
        collection.flush()
        print("    Delete: OK")

        return True

    except Exception as e:
        print(f"    Test failed: {e}")
        # Cleanup on failure
        try:
            collection.delete(f'chunk_uuid == "{test_uuid}"')
            collection.flush()
        except Exception:
            pass
        return False


def main(reset: bool = False, verify_only: bool = False) -> int:
    """Main function."""
    print("\n" + "=" * 60)
    print("  Milvus Collection Initialization")
    print("=" * 60)

    try:
        connect_milvus()
    except Exception as e:
        print(f"\n  Connection failed: {e}")
        print("\n  Tips:")
        print("    1. Ensure Milvus is running: docker compose ps")
        print("    2. Check port: MILVUS_PORT in .env")
        return 1

    try:
        # Verify only mode
        if verify_only:
            print("\n  Mode: Verify Only")
            if not utility.has_collection(COLLECTION_NAME):
                print(f"\n  Collection '{COLLECTION_NAME}' does not exist")
                return 1
            collection = Collection(COLLECTION_NAME)
            print("-" * 60)
            verify_collection(collection)
            print("-" * 60)
            print("\n  Verification: PASSED")
            return 0

        # Reset mode
        if reset:
            print("\n  Mode: Reset (DROP + CREATE)")
        else:
            print("\n  Mode: Initialize (CREATE IF NOT EXISTS)")

        print("-" * 60)

        # Create/get collection
        collection = create_collection(reset=reset)

        # Create indexes if needed
        if reset or not collection.indexes:
            create_indexes(collection)

        # Verify
        verify_collection(collection)

        # Run functional test
        print("-" * 60)
        test_ok = run_insert_search_test(collection)

        print("-" * 60)
        if test_ok:
            print("\n  Initialization: SUCCESS")
            return 0
        else:
            print("\n  Initialization: FAILED (test error)")
            return 1

    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        connections.disconnect("default")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize Milvus collection for Knowledge Store"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop collection and recreate (WARNING: Data loss!)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify existing collection without changes",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.reset:
        print("\n  WARNING: This will DELETE ALL DATA in the collection!")
        print("  Press Ctrl+C to cancel, or wait 3 seconds to continue...")
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            sys.exit(0)

    try:
        exit_code = main(reset=args.reset, verify_only=args.verify)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user")
        sys.exit(130)
