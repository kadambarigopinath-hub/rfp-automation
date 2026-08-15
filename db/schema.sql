-- RFP Automation Platform - Initial Schema
-- Postgres 16+ with pgvector extension

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ========== IDENTITY & ACCESS ==========

CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

INSERT INTO roles (name) VALUES
 ('legal'), ('infosec'), ('infrastructure'), ('product'),
 ('business'), ('engineering'), ('superadmin'), ('rfp_agent_service');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INT REFERENCES roles(id) NOT NULL,
    mfa_secret TEXT,
    active BOOLEAN DEFAULT TRUE,
    failed_login_attempts INT DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    ip_address TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- ========== FOLDERS & PERMISSIONS ==========

CREATE TABLE folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    folder_type TEXT NOT NULL CHECK (folder_type IN ('kb_persona', 'rfp')),
    owner_role_id INT REFERENCES roles(id),
    archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE folder_permissions (
    folder_id UUID REFERENCES folders(id) ON DELETE CASCADE,
    role_id INT REFERENCES roles(id),
    can_view BOOLEAN DEFAULT FALSE,
    can_add BOOLEAN DEFAULT FALSE,
    can_update BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_download BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (folder_id, role_id)
);

CREATE TABLE tag_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id UUID REFERENCES folders(id) ON DELETE CASCADE,
    tag_key TEXT NOT NULL,
    allowed_values TEXT[],
    required BOOLEAN DEFAULT FALSE,
    UNIQUE(folder_id, tag_key)
);

-- ========== KNOWLEDGE BASE DOCUMENTS ==========

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id UUID REFERENCES folders(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    doctype TEXT,
    current_version_id UUID,
    status TEXT DEFAULT 'active' CHECK (status IN ('active','deleted')),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE document_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    storage_key TEXT NOT NULL,
    file_type TEXT,
    file_size_bytes BIGINT,
    content_sha256 TEXT NOT NULL,
    content_simhash BIGINT,
    uploaded_by UUID REFERENCES users(id),
    change_note TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(document_id, version_number)
);
CREATE INDEX idx_document_versions_sha256 ON document_versions(content_sha256);
CREATE INDEX idx_document_versions_simhash ON document_versions(content_simhash);

ALTER TABLE documents
  ADD CONSTRAINT fk_current_version FOREIGN KEY (current_version_id) REFERENCES document_versions(id);

CREATE TABLE document_tags (
    document_version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
    tag_key TEXT NOT NULL,
    tag_value TEXT NOT NULL,
    PRIMARY KEY (document_version_id, tag_key)
);

CREATE TABLE document_embeddings (
    id BIGSERIAL PRIMARY KEY,
    document_version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024),
    metadata JSONB
);
CREATE INDEX idx_doc_embeddings_vector ON document_embeddings
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE document_centroids (
    document_version_id UUID PRIMARY KEY REFERENCES document_versions(id) ON DELETE CASCADE,
    centroid VECTOR(1024)
);

-- ========== UNIVERSAL CHANGE HISTORY ==========

CREATE TABLE change_history (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_by UUID REFERENCES users(id),
    changed_by_type TEXT CHECK (changed_by_type IN ('user','ai','system')) NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_change_history_entity ON change_history(entity_type, entity_id, changed_at);

-- ========== RISK FLAGGING (per persona, post-intake) ==========

CREATE TABLE risk_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID,
    persona_role_id INT REFERENCES roles(id),
    risk_text TEXT NOT NULL,
    source_clause_ref TEXT,
    severity TEXT CHECK (severity IN ('low','medium','high')),
    status TEXT DEFAULT 'open' CHECK (status IN ('open','edited','added_to_prebid','dismissed','under_review','closed')),
    added_to_prebid_question_id UUID,
    created_by TEXT CHECK (created_by IN ('ai','user')),
    edited_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_risk_flags_persona ON risk_flags(persona_role_id, status);

CREATE TABLE risk_review_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_flag_id UUID REFERENCES risk_flags(id) ON DELETE CASCADE,
    assigned_role_id INT REFERENCES roles(id) NOT NULL,
    assigned_by UUID REFERENCES users(id),
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','in_review','closed')),
    closed_by UUID REFERENCES users(id),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_risk_assignments_role_status ON risk_review_assignments(assigned_role_id, status);

CREATE TABLE risk_flag_comments (
    id BIGSERIAL PRIMARY KEY,
    risk_flag_id UUID REFERENCES risk_flags(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    comment_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_risk_comments_flag ON risk_flag_comments(risk_flag_id);

-- ========== RFP PROJECTS ==========

CREATE TABLE rfp_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id UUID REFERENCES folders(id),
    customer_name TEXT NOT NULL,
    product_service_name TEXT,
    rfp_number TEXT,
    rfp_date DATE,
    status TEXT DEFAULT 'in_progress',
    archived BOOLEAN DEFAULT FALSE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE risk_flags ADD CONSTRAINT fk_risk_rfp FOREIGN KEY (rfp_id) REFERENCES rfp_projects(id) ON DELETE CASCADE;

CREATE TABLE rfp_status_comments (
    id BIGSERIAL PRIMARY KEY,
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    comment TEXT,
    status_value TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE rfp_source_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),
    is_required BOOLEAN DEFAULT TRUE,
    received BOOLEAN DEFAULT FALSE,
    skipped_by_user BOOLEAN DEFAULT FALSE,
    referenced_but_missing_note TEXT
);

CREATE TABLE rfp_agent_state (
    rfp_id UUID PRIMARY KEY REFERENCES rfp_projects(id) ON DELETE CASCADE,
    current_step TEXT NOT NULL,
    step_data JSONB,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE eligibility_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    requirement_text TEXT NOT NULL,
    status TEXT CHECK (status IN ('meet','dont_meet','need_more_info')),
    remarks TEXT,
    created_by TEXT CHECK (created_by IN ('ai','user')),
    last_updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE prebid_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    sno INT,
    clause_no TEXT,
    source_document_ref TEXT,
    clause_text TEXT,
    clarification_requested TEXT,
    is_exception_request BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'draft',
    created_by TEXT CHECK (created_by IN ('ai','user')),
    last_updated_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE risk_flags ADD CONSTRAINT fk_risk_prebid FOREIGN KEY (added_to_prebid_question_id) REFERENCES prebid_questions(id);

CREATE TABLE assessment_criteria (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    criteria_text TEXT,
    max_score NUMERIC,
    step_scores JSONB
);

CREATE TABLE rfp_chat_messages (
    id BIGSERIAL PRIMARY KEY,
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    sender_type TEXT CHECK (sender_type IN ('user','agent')),
    message TEXT,
    step_context TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE company_branding (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    logo_storage_key TEXT,
    footer_text TEXT,
    updated_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ DEFAULT now(),
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE rfp_response_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_reference_id TEXT UNIQUE NOT NULL,
    rfp_id UUID REFERENCES rfp_projects(id) ON DELETE CASCADE,
    doc_type TEXT CHECK (doc_type IN ('risk_report','prebid_questions','response_draft','final_response')),
    storage_key TEXT NOT NULL,
    version_number INT NOT NULL,
    generated_by TEXT CHECK (generated_by IN ('ai','user')),
    uploaded_by UUID REFERENCES users(id),
    branding_id UUID REFERENCES company_branding(id),
    is_final BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(rfp_id, doc_type, version_number)
);

CREATE UNIQUE INDEX idx_one_final_per_doctype
  ON rfp_response_documents(rfp_id, doc_type)
  WHERE is_final = TRUE;

CREATE TABLE content_provenance (
    id BIGSERIAL PRIMARY KEY,
    response_document_id UUID REFERENCES rfp_response_documents(id) ON DELETE CASCADE,
    section_ref TEXT,
    author_type TEXT CHECK (author_type IN ('ai','user')),
    user_id UUID REFERENCES users(id),
    content_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ========== INDEXES ==========
CREATE INDEX idx_documents_folder ON documents(folder_id);
CREATE INDEX idx_rfp_projects_status ON rfp_projects(status, archived);
CREATE INDEX idx_prebid_rfp ON prebid_questions(rfp_id);
CREATE INDEX idx_eligibility_rfp ON eligibility_requirements(rfp_id);
CREATE INDEX idx_chat_rfp ON rfp_chat_messages(rfp_id, created_at);
