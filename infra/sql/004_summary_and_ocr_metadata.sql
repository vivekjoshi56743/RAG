-- Quality improvements: richer document summaries + OCR provenance on chunks.
-- Safe to run on existing data; all new columns are nullable with no backfill.

BEGIN;

-- Document summary enrichment: named entities + free-text subtype.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS entities JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS subtype  TEXT;

-- Chunk provenance: which extraction path produced this text?
--   'native'        — PyMuPDF / native PDF or text extraction
--   'ocr'           — Cloud Vision OCR, normal confidence
--   'ocr_low_conf'  — Cloud Vision OCR, flagged low confidence
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS source_type TEXT;

-- Partial index: small set of chunks marked as OCR, useful for quality audits.
CREATE INDEX IF NOT EXISTS chunks_source_type_idx
    ON chunks(source_type)
    WHERE source_type IS NOT NULL;

COMMIT;
