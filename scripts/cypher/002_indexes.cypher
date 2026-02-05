// =============================================================================
// Knowledge Store Neo4j Schema - Indexes
// =============================================================================
// Version: 1.0.0
// Date: 2026-01-28
// Description: Search and filter indexes for all node types
// =============================================================================

// =============================================================================
// Document Indexes
// =============================================================================

// Document title index for text search
CREATE INDEX doc_title_idx IF NOT EXISTS
FOR (d:Document) ON (d.title);

// Document source index for filtering
CREATE INDEX doc_source_idx IF NOT EXISTS
FOR (d:Document) ON (d.source);

// Document security level index
CREATE INDEX doc_security_idx IF NOT EXISTS
FOR (d:Document) ON (d.security_level);

// Document status index
CREATE INDEX doc_status_idx IF NOT EXISTS
FOR (d:Document) ON (d.status);

// Document created_at index for sorting
CREATE INDEX doc_created_idx IF NOT EXISTS
FOR (d:Document) ON (d.created_at);

// =============================================================================
// Chunk Indexes
// =============================================================================

// Chunk text preview index for search
CREATE INDEX chunk_text_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.text_preview);

// Chunk sequence index for ordering
CREATE INDEX chunk_sequence_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.sequence);

// Chunk section path index
CREATE INDEX chunk_section_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.section_path);

// =============================================================================
// Person Indexes
// =============================================================================

// Person name index for search
CREATE INDEX person_name_idx IF NOT EXISTS
FOR (p:Person) ON (p.name);

// Person department index for filtering
CREATE INDEX person_dept_idx IF NOT EXISTS
FOR (p:Person) ON (p.department);

// Person role index
CREATE INDEX person_role_idx IF NOT EXISTS
FOR (p:Person) ON (p.role);

// Person email index
CREATE INDEX person_email_idx IF NOT EXISTS
FOR (p:Person) ON (p.email);

// =============================================================================
// Organization Indexes
// =============================================================================

// Organization name index
CREATE INDEX org_name_idx IF NOT EXISTS
FOR (o:Organization) ON (o.name);

// Organization parent index for hierarchy traversal
CREATE INDEX org_parent_idx IF NOT EXISTS
FOR (o:Organization) ON (o.parent_org_id);

// =============================================================================
// Project Indexes
// =============================================================================

// Project name index
CREATE INDEX project_name_idx IF NOT EXISTS
FOR (proj:Project) ON (proj.name);

// Project status index
CREATE INDEX project_status_idx IF NOT EXISTS
FOR (proj:Project) ON (proj.status);

// =============================================================================
// Policy Indexes
// =============================================================================

// Policy name index
CREATE INDEX policy_name_idx IF NOT EXISTS
FOR (pol:Policy) ON (pol.name);

// Policy effective date index
CREATE INDEX policy_effective_idx IF NOT EXISTS
FOR (pol:Policy) ON (pol.effective_from);

// =============================================================================
// Concept Indexes (for Knowledge Graph)
// =============================================================================

// Concept name index
CREATE INDEX concept_name_idx IF NOT EXISTS
FOR (con:Concept) ON (con.name);

// Concept type index
CREATE INDEX concept_type_idx IF NOT EXISTS
FOR (con:Concept) ON (con.type);

// =============================================================================
// Topic Indexes
// =============================================================================

// Topic name index
CREATE INDEX topic_name_idx IF NOT EXISTS
FOR (t:Topic) ON (t.name);

// =============================================================================
// Full-text Search Indexes (for advanced text search)
// =============================================================================

// Full-text index on Document title (for fuzzy search)
CREATE FULLTEXT INDEX doc_title_fulltext IF NOT EXISTS
FOR (d:Document) ON EACH [d.title];

// Full-text index on Person name
CREATE FULLTEXT INDEX person_name_fulltext IF NOT EXISTS
FOR (p:Person) ON EACH [p.name];
