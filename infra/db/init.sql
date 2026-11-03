-- Runs once, on first start of an empty database volume.
-- Alembic migrations will also ensure this exists; this makes a fresh DB usable immediately.
CREATE EXTENSION IF NOT EXISTS vector;
