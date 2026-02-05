// =============================================================================
// Knowledge Store Neo4j Schema - Constraints
// =============================================================================
// Version: 1.0.0
// Date: 2026-01-28
// Description: Unique constraints for all node types
// =============================================================================

// =============================================================================
// Document Constraints
// =============================================================================

// Document - doc_uuid must be unique
CREATE CONSTRAINT doc_uuid_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_uuid IS UNIQUE;

// =============================================================================
// Chunk Constraints
// =============================================================================

// Chunk - chunk_uuid must be unique
CREATE CONSTRAINT chunk_uuid_unique IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_uuid IS UNIQUE;

// =============================================================================
// Person Constraints
// =============================================================================

// Person - emp_id must be unique
CREATE CONSTRAINT person_emp_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.emp_id IS UNIQUE;

// =============================================================================
// Organization Constraints
// =============================================================================

// Organization - org_id must be unique
CREATE CONSTRAINT org_id_unique IF NOT EXISTS
FOR (o:Organization) REQUIRE o.org_id IS UNIQUE;

// =============================================================================
// Project Constraints
// =============================================================================

// Project - project_id must be unique
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (proj:Project) REQUIRE proj.project_id IS UNIQUE;

// =============================================================================
// Policy Constraints
// =============================================================================

// Policy - policy_id must be unique
CREATE CONSTRAINT policy_id_unique IF NOT EXISTS
FOR (pol:Policy) REQUIRE pol.policy_id IS UNIQUE;

// =============================================================================
// Concept Constraints (for Knowledge Graph)
// =============================================================================

// Concept - concept_id must be unique
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS
FOR (con:Concept) REQUIRE con.concept_id IS UNIQUE;

// =============================================================================
// Topic Constraints
// =============================================================================

// Topic - topic_id must be unique
CREATE CONSTRAINT topic_id_unique IF NOT EXISTS
FOR (t:Topic) REQUIRE t.topic_id IS UNIQUE;
