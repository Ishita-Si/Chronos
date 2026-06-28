-- CHRONOS unified plant memory (Temporal Knowledge Graph + evidence store).
-- A property-graph modelled on SQLite: nodes are typed tables, relationships
-- live in the generic `edges` table, every fact carries time validity and a
-- confidence score so retrieval can be trust-ranked and time-travelled.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---- Nodes ----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assets (
    asset_id    TEXT PRIMARY KEY,      -- e.g. P-204
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,         -- pump | heat_exchanger | compressor ...
    area        TEXT,
    criticality TEXT,                  -- A | B | C
    install_date TEXT
);

CREATE TABLE IF NOT EXISTS persons (
    person_id TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    role      TEXT
);

-- Every alarm, reading, work order, inspection, bypass, trip becomes an Event
-- in one common schema (Module 1: event normalization).
CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,
    asset_id   TEXT NOT NULL,
    ts         TEXT NOT NULL,          -- ISO timestamp (occurrence)
    etype      TEXT NOT NULL,          -- READING|ALARM|WORKORDER|INSPECTION|BYPASS|TRIP
    subtype    TEXT,                   -- vibration_high, seal_replacement ...
    param      TEXT,                   -- pressure, temperature, vibration ...
    value      REAL,
    unit       TEXT,
    severity   TEXT,                   -- info|warn|high|critical
    status     TEXT,                   -- open|closed|done|deferred
    text       TEXT,                   -- free-text note / alarm message / WO desc
    person_id  TEXT,
    source     TEXT NOT NULL,          -- scada|dcs_alarms|cmms|inspection|sop
    source_ref TEXT NOT NULL,          -- citable pointer back to original record
    confidence REAL DEFAULT 1.0,
    valid_from TEXT,
    valid_to   TEXT,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id)
);
CREATE INDEX IF NOT EXISTS idx_events_asset_ts ON events(asset_id, ts);
CREATE INDEX IF NOT EXISTS idx_events_etype ON events(etype);

CREATE TABLE IF NOT EXISTS documents (
    doc_id     TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    type       TEXT NOT NULL,          -- sop | oem_manual | inspection_report
    path       TEXT,
    version    TEXT,
    valid_from TEXT,
    valid_to   TEXT,
    supersedes TEXT,                   -- doc_id of older revision (DOC_SUPERSEDES_DOC)
    text       TEXT
);

-- Retrievable passages: chunks of documents + textual events. This is the
-- corpus the vector store indexes (semantic retrieval) and what citations
-- point back to (evidence store).
CREATE TABLE IF NOT EXISTS passages (
    passage_id TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,          -- sop_chunk | manual_chunk | inspection | alarm | workorder
    asset_id   TEXT,
    ts         TEXT,
    title      TEXT,
    text       TEXT NOT NULL,
    source_ref TEXT NOT NULL,          -- human-readable citation target
    doc_id     TEXT,
    event_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_passages_asset ON passages(asset_id);

-- Compliance / quality clauses (Module 6).
CREATE TABLE IF NOT EXISTS clauses (
    clause_id        TEXT PRIMARY KEY,
    standard         TEXT NOT NULL,    -- OISD-130, Factory Act, PESO ...
    title            TEXT NOT NULL,
    text             TEXT,
    evidence_type    TEXT,             -- inspection subtype that satisfies it
    frequency_days   INTEGER,          -- required cadence
    applies_to_type  TEXT              -- asset type the clause governs
);

-- ---- Relationships (the graph edges) --------------------------------------
-- Generic temporal property-graph edge table.
CREATE TABLE IF NOT EXISTS edges (
    edge_id    TEXT PRIMARY KEY,
    src_type   TEXT NOT NULL,
    src_id     TEXT NOT NULL,
    rel        TEXT NOT NULL,          -- ASSET_HAS_EVENT, EVENT_REFERENCES_DOC ...
    dst_type   TEXT NOT NULL,
    dst_id     TEXT NOT NULL,
    valid_from TEXT,
    valid_to   TEXT,
    confidence REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_type, src_id, rel);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_type, dst_id, rel);

-- Data lineage / provenance for every ingested record (Module 1).
CREATE TABLE IF NOT EXISTS lineage (
    record_id   TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_ref  TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0
);
