-- =============================================================================
-- Knowledge Store PostgreSQL Schema
-- =============================================================================
-- Version: 1.0.0
-- Date: 2026-01-28
-- Description: Core tables for document management, versioning, ACL, and audit
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. Documents Table (정본 관리)
-- =============================================================================
-- Central table for managing document metadata and ownership
CREATE TABLE IF NOT EXISTS documents (
    doc_uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    source          VARCHAR(50) NOT NULL CHECK (source IN ('wiki', 'agit', 'gdocs', 'slack', 'confluence', 'notion', 'file')),
    source_url      VARCHAR(2000) NOT NULL,
    owner_id        VARCHAR(100) NOT NULL,
    owner_org       VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    security_level  VARCHAR(20) NOT NULL DEFAULT 'internal' CHECK (security_level IN ('public', 'internal', 'confidential')),
    current_version_id UUID,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE documents IS 'Central table for document metadata and ownership';
COMMENT ON COLUMN documents.doc_uuid IS 'Unique document identifier';
COMMENT ON COLUMN documents.source IS 'Document source system (wiki, agit, gdocs, slack, confluence, notion, file)';
COMMENT ON COLUMN documents.status IS 'Document status (draft, published, archived)';
COMMENT ON COLUMN documents.security_level IS 'Security classification (public, internal, confidential)';
COMMENT ON COLUMN documents.current_version_id IS 'Reference to current active version';

-- Documents Indexes
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_owner_org ON documents(owner_org);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_security ON documents(security_level);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_updated ON documents(updated_at DESC);

-- =============================================================================
-- 2. Document Versions Table (버전 관리)
-- =============================================================================
-- Tracks all versions of each document
CREATE TABLE IF NOT EXISTS document_versions (
    version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    content_size    BIGINT,
    effective_from  TIMESTAMP WITH TIME ZONE,
    effective_until TIMESTAMP WITH TIME ZONE,
    approved_by     VARCHAR(100),
    approval_date   TIMESTAMP WITH TIME ZONE,
    change_summary  TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, version_no)
);

COMMENT ON TABLE document_versions IS 'Tracks document version history';
COMMENT ON COLUMN document_versions.version_no IS 'Sequential version number per document';
COMMENT ON COLUMN document_versions.content_hash IS 'SHA-256 hash of document content';
COMMENT ON COLUMN document_versions.effective_from IS 'When this version becomes effective';
COMMENT ON COLUMN document_versions.effective_until IS 'When this version expires (null = current)';

-- Versions Indexes
CREATE INDEX IF NOT EXISTS idx_versions_doc ON document_versions(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_versions_doc_no ON document_versions(doc_uuid, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_versions_effective ON document_versions(effective_from);
CREATE INDEX IF NOT EXISTS idx_versions_hash ON document_versions(content_hash);

-- =============================================================================
-- 3. Document Chunks Table (청크 ID 매핑)
-- =============================================================================
-- Maps document chunks to Milvus vectors and Neo4j nodes
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_uuid      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    chunk_no        INTEGER NOT NULL,
    section_path    VARCHAR(500),
    chunk_text      TEXT,
    char_start      INTEGER,
    char_end        INTEGER,
    token_count     INTEGER,
    milvus_id       VARCHAR(100),
    neo4j_node_id   VARCHAR(100),
    embedding_model VARCHAR(100),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(version_id, chunk_no)
);

COMMENT ON TABLE document_chunks IS 'Maps document chunks to vector DB and graph DB';
COMMENT ON COLUMN document_chunks.chunk_no IS 'Sequential chunk number within a version';
COMMENT ON COLUMN document_chunks.section_path IS 'Hierarchical section path (e.g., "1.2.3 Overview")';
COMMENT ON COLUMN document_chunks.milvus_id IS 'Vector ID in Milvus collection';
COMMENT ON COLUMN document_chunks.neo4j_node_id IS 'Node ID in Neo4j graph';

-- Chunks Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON document_chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_chunks_milvus ON document_chunks(milvus_id) WHERE milvus_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_neo4j ON document_chunks(neo4j_node_id) WHERE neo4j_node_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chunks_section ON document_chunks(section_path);

-- =============================================================================
-- 4. ACL Entries Table (권한 관리)
-- =============================================================================
-- Access Control List for document permissions
CREATE TABLE IF NOT EXISTS acl_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    principal_type  VARCHAR(20) NOT NULL CHECK (principal_type IN ('user', 'group', 'org', 'role')),
    principal_id    VARCHAR(100) NOT NULL,
    permission      VARCHAR(20) NOT NULL CHECK (permission IN ('read', 'write', 'admin', 'delete')),
    granted_by      VARCHAR(100),
    expires_at      TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, principal_type, principal_id, permission)
);

COMMENT ON TABLE acl_entries IS 'Access Control List for document permissions';
COMMENT ON COLUMN acl_entries.principal_type IS 'Type of principal (user, group, org, role)';
COMMENT ON COLUMN acl_entries.permission IS 'Permission level (read, write, admin, delete)';

-- ACL Indexes
CREATE INDEX IF NOT EXISTS idx_acl_doc ON acl_entries(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_acl_principal ON acl_entries(principal_type, principal_id);
CREATE INDEX IF NOT EXISTS idx_acl_permission ON acl_entries(permission);
CREATE INDEX IF NOT EXISTS idx_acl_expires ON acl_entries(expires_at) WHERE expires_at IS NOT NULL;

-- =============================================================================
-- 5. Audit Logs Table (감사 로그)
-- =============================================================================
-- Tracks all user actions for compliance and debugging
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(100) NOT NULL,
    user_org        VARCHAR(100),
    action          VARCHAR(50) NOT NULL CHECK (action IN ('search', 'view', 'create', 'update', 'delete', 'export', 'share', 'permission_change')),
    resource_type   VARCHAR(50) NOT NULL DEFAULT 'document' CHECK (resource_type IN ('document', 'chunk', 'acl', 'system')),
    doc_uuid        UUID,
    query_text      TEXT,
    retrieved_docs  UUID[],
    result_count    INTEGER,
    response_time_ms INTEGER,
    ip_address      INET,
    user_agent      VARCHAR(500),
    metadata        JSONB DEFAULT '{}',
    timestamp       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE audit_logs IS 'Audit trail for all user actions';
COMMENT ON COLUMN audit_logs.action IS 'Type of action performed';
COMMENT ON COLUMN audit_logs.resource_type IS 'Type of resource affected';
COMMENT ON COLUMN audit_logs.retrieved_docs IS 'Array of document UUIDs returned in search';
COMMENT ON COLUMN audit_logs.metadata IS 'Additional context as JSON';

-- Audit Indexes
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_user_org ON audit_logs(user_org) WHERE user_org IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type);
CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_logs(doc_uuid) WHERE doc_uuid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_metadata ON audit_logs USING gin(metadata);

-- Partition audit_logs by timestamp for better performance (optional, for large scale)
-- Consider partitioning by month if table grows large

-- =============================================================================
-- 6. Add FK for current_version_id (Circular Reference Resolution)
-- =============================================================================
-- Add foreign key after both tables exist to avoid circular dependency
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_current_version'
    ) THEN
        ALTER TABLE documents
            ADD CONSTRAINT fk_current_version
            FOREIGN KEY (current_version_id)
            REFERENCES document_versions(version_id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- =============================================================================
-- 7. Updated_at Trigger Function
-- =============================================================================
-- Automatically update updated_at column on row modification
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to documents table
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- 8. Version Validation Trigger
-- =============================================================================
-- Ensure version_no increments correctly
CREATE OR REPLACE FUNCTION validate_version_number()
RETURNS TRIGGER AS $$
DECLARE
    max_version INTEGER;
BEGIN
    SELECT COALESCE(MAX(version_no), 0) INTO max_version
    FROM document_versions
    WHERE doc_uuid = NEW.doc_uuid;

    IF NEW.version_no != max_version + 1 THEN
        RAISE EXCEPTION 'Version number must be sequential. Expected %, got %',
            max_version + 1, NEW.version_no;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS validate_version_number_trigger ON document_versions;
CREATE TRIGGER validate_version_number_trigger
    BEFORE INSERT ON document_versions
    FOR EACH ROW
    EXECUTE FUNCTION validate_version_number();

-- =============================================================================
-- Schema Complete
-- =============================================================================
