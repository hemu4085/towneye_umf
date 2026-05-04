-- [FILE PATH]: /towneye_umf/schemas/gold/party_model.sql
-- Date: 2026-02-28
-- Execution Mode: Schema-First Architecture

CREATE TABLE gold.te_party (
    te_party_pk BIGINT PRIMARY KEY,
    party_type VARCHAR(20) CHECK (party_type IN ('INDIVIDUAL', 'ORGANIZATION')),
    legal_name VARCHAR(255),
    te_id UUID DEFAULT gen_random_uuid(),
    te_source VARCHAR(100),
    te_timestamp TIMESTAMPTZ DEFAULT NOW(),
    te_geo_hash VARCHAR(12)
);

CREATE TABLE gold.te_party_relationship (
    te_rel_pk BIGINT PRIMARY KEY,
    from_party_pk BIGINT REFERENCES gold.te_party(te_party_pk),
    to_party_pk BIGINT REFERENCES gold.te_party(te_party_pk),
    relationship_type VARCHAR(50)
);
