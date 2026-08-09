"""initial schema (PRD section 6)

Revision ID: 0001
Revises:
Create Date: 2026-08-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.config import get_settings

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = get_settings().EMBEDDING_DIM


def upgrade() -> None:
    # citext is required for users.email (case-insensitive unique); vector for
    # the evidence embedding column. Both must exist before the tables below.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            email CITEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            avatar_url TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE refresh_tokens (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ
        );
        """
    )

    op.execute(
        """
        CREATE TABLE research_runs (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            query TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            plan JSONB,
            started_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ,
            input_tokens INT DEFAULT 0,
            output_tokens INT DEFAULT 0,
            cost_estimate_usd NUMERIC(10,5) DEFAULT 0,
            latency_seconds NUMERIC(10,2)
        );
        """
    )
    op.execute("CREATE INDEX ON research_runs (user_id, started_at DESC);")

    op.execute(
        """
        CREATE TABLE sources (
            id UUID PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            url TEXT NOT NULL,
            title TEXT,
            domain TEXT,
            source_type TEXT,
            publication_date TEXT,
            credibility_score FLOAT,
            fetched_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (run_id, url)
        );
        """
    )

    op.execute(
        f"""
        CREATE TABLE evidence (
            id UUID PRIMARY KEY,
            run_id UUID NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
            source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            claim TEXT NOT NULL,
            relevant_excerpt TEXT NOT NULL DEFAULT '',
            confidence FLOAT,
            agent TEXT,
            topic TEXT,
            numeric_value DOUBLE PRECISION,
            numeric_unit TEXT,
            time_period TEXT,
            embedding VECTOR({EMBEDDING_DIM}),
            metadata JSONB DEFAULT '{{}}'::jsonb,
            search_tsv tsvector GENERATED ALWAYS AS (
                to_tsvector('english', coalesce(claim,'') || ' ' || coalesce(relevant_excerpt,''))
            ) STORED
        );
        """
    )
    op.execute("CREATE INDEX evidence_embedding_idx ON evidence USING hnsw (embedding vector_cosine_ops);")
    op.execute("CREATE INDEX evidence_tsv_idx ON evidence USING GIN (search_tsv);")
    op.execute("CREATE INDEX ON evidence (run_id, topic);")

    op.execute(
        """
        CREATE TABLE fact_check_results (
            id UUID PRIMARY KEY,
            run_id UUID REFERENCES research_runs(id) ON DELETE CASCADE,
            evidence_id UUID REFERENCES evidence(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            verifying_source_url TEXT,
            notes TEXT
        );
        """
    )

    op.execute(
        """
        CREATE TABLE contradictions (
            id UUID PRIMARY KEY,
            run_id UUID REFERENCES research_runs(id) ON DELETE CASCADE,
            topic TEXT,
            evidence_a_id UUID REFERENCES evidence(id),
            evidence_b_id UUID REFERENCES evidence(id),
            explanation TEXT,
            resolved BOOLEAN DEFAULT false
        );
        """
    )

    op.execute(
        """
        CREATE TABLE figures (
            id UUID PRIMARY KEY,
            run_id UUID REFERENCES research_runs(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('chart','diagram','source_image')),
            caption TEXT NOT NULL,
            alt_text TEXT NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            spec JSONB,
            evidence_ids UUID[] NOT NULL,
            source_id UUID REFERENCES sources(id),
            license_note TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT figure_must_be_attributed CHECK (cardinality(evidence_ids) > 0)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE reports (
            id UUID PRIMARY KEY,
            run_id UUID REFERENCES research_runs(id) ON DELETE CASCADE,
            content_markdown TEXT NOT NULL,
            citations JSONB NOT NULL,
            figure_ids UUID[] DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE node_traces (
            id UUID PRIMARY KEY,
            run_id UUID REFERENCES research_runs(id) ON DELETE CASCADE,
            node_name TEXT NOT NULL,
            seq INT NOT NULL,
            input JSONB, output JSONB,
            input_tokens INT DEFAULT 0, output_tokens INT DEFAULT 0,
            latency_ms INT, cost_usd NUMERIC(10,6),
            status TEXT, error TEXT,
            started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX ON node_traces (run_id, seq);")

    op.execute(
        """
        CREATE TABLE eval_runs (
            id UUID PRIMARY KEY,
            dataset_version TEXT,
            metrics JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE user_preferences (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            preferred_mode TEXT,
            preferred_source_types TEXT[],
            preferred_report_format TEXT
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_preferences;")
    op.execute("DROP TABLE IF EXISTS eval_runs;")
    op.execute("DROP TABLE IF EXISTS node_traces;")
    op.execute("DROP TABLE IF EXISTS reports;")
    op.execute("DROP TABLE IF EXISTS figures;")
    op.execute("DROP TABLE IF EXISTS contradictions;")
    op.execute("DROP TABLE IF EXISTS fact_check_results;")
    op.execute("DROP TABLE IF EXISTS evidence;")
    op.execute("DROP TABLE IF EXISTS sources;")
    op.execute("DROP TABLE IF EXISTS research_runs;")
    op.execute("DROP TABLE IF EXISTS refresh_tokens;")
    op.execute("DROP TABLE IF EXISTS users;")
