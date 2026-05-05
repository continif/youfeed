"""activity_log partitioned + helper functions per gestione partizioni daily

Revision ID: 0004_activity_log
Revises: 0003_articles_kg
Create Date: 2026-05-05

"""

from __future__ import annotations

from typing import Sequence

from alembic import op

revision: str = "0004_activity_log"
down_revision: str | Sequence[str] | None = "0003_articles_kg"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tabella partizionata per giorno. Le partizioni effettive vengono create
    # dal worker `manage_partitions` (funzione SQL `yf_create_activity_partition`).
    op.execute(
        """
        CREATE TABLE activity_log (
            id              BIGSERIAL,
            user_id         BIGINT,
            session_id      UUID,
            fingerprint     TEXT,
            event_type      VARCHAR(32) NOT NULL,
            route           TEXT,
            method          VARCHAR(8),
            target_type     VARCHAR(16),
            target_id       TEXT,
            metadata        JSONB,
            ip              INET,
            country         VARCHAR(8),
            asn             INTEGER,
            ua              TEXT,
            status          INTEGER,
            latency_ms      INTEGER,
            ts              TIMESTAMPTZ NOT NULL,
            CONSTRAINT pk_activity_log PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts);
        """
    )

    op.execute(
        """
        CREATE INDEX ix_activity_log_user_ts
            ON activity_log (user_id, ts DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX ix_activity_log_target
            ON activity_log (target_type, target_id);
        """
    )

    # Funzione helper: crea una partizione daily per la data data.
    # Idempotente: usa CREATE TABLE IF NOT EXISTS.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION yf_create_activity_partition(p_date DATE)
        RETURNS VOID AS $$
        DECLARE
            partition_name TEXT;
            range_start TEXT;
            range_end TEXT;
        BEGIN
            partition_name := 'activity_log_' || to_char(p_date, 'YYYY_MM_DD');
            range_start := to_char(p_date, 'YYYY-MM-DD');
            range_end := to_char(p_date + INTERVAL '1 day', 'YYYY-MM-DD');

            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF activity_log
                 FOR VALUES FROM (%L) TO (%L)',
                partition_name, range_start, range_end
            );
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Funzione helper: drop di tutte le partizioni più vecchie di N giorni.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION yf_drop_old_activity_partitions(p_keep_days INT)
        RETURNS INT AS $$
        DECLARE
            cutoff DATE;
            r RECORD;
            dropped INT := 0;
        BEGIN
            cutoff := CURRENT_DATE - p_keep_days;
            FOR r IN
                SELECT inhrelid::regclass::text AS partition_name
                FROM pg_inherits
                WHERE inhparent = 'activity_log'::regclass
            LOOP
                -- Estraiamo la data dal nome partizione (formato activity_log_YYYY_MM_DD)
                IF r.partition_name ~ 'activity_log_\\d{4}_\\d{2}_\\d{2}$' THEN
                    IF to_date(
                        regexp_replace(r.partition_name, '.*activity_log_', ''),
                        'YYYY_MM_DD'
                    ) < cutoff THEN
                        EXECUTE format('DROP TABLE %I', r.partition_name);
                        dropped := dropped + 1;
                    END IF;
                END IF;
            END LOOP;
            RETURN dropped;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Crea le partizioni di oggi + 7 giorni futuri come bootstrap.
    op.execute(
        """
        DO $$
        DECLARE
            d DATE;
        BEGIN
            FOR d IN SELECT generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', INTERVAL '1 day')::date LOOP
                PERFORM yf_create_activity_partition(d);
            END LOOP;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS yf_drop_old_activity_partitions(INT)")
    op.execute("DROP FUNCTION IF EXISTS yf_create_activity_partition(DATE)")
    op.execute("DROP TABLE IF EXISTS activity_log CASCADE")
