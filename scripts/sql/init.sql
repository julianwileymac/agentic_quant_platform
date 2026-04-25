-- Minimal Postgres bootstrap — most tables are created via SQLAlchemy,
-- but we pre-create extensions and a readonly role for the MLflow UI.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- MLflow writes its own tables into the same DB; nothing to pre-create.
