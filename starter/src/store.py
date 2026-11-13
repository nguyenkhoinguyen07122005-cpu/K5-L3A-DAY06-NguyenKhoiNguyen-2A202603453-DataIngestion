"""PostgreSQL + pgvector store: persistent vectors, exact cosine search, SQL metadata filter."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
import numpy as np

from .models import Chunk

TABLE = "day6_chunks"
# Only these columns may be used in filters (whitelist -> no SQL injection via keys).
FILTERABLE = {"document_id", "pep_type", "status", "python_version", "created_year", "section"}


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is empty: copy .env.example to .env")
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.url = database_url
        self.dimensions = dimensions
        self.conn = psycopg.connect(database_url, connect_timeout=5, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname='vector'")
            row = cur.fetchone()
            if not row:
                raise RuntimeError("pgvector extension missing in this database")
            self.pgvector_version = row[0]
            cur.execute("SHOW server_version")
            self.server_version = cur.fetchone()[0]
        register_vector(self.conn)

    def create_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    strategy        text        NOT NULL,
                    chunk_id        text        NOT NULL,
                    document_id     text        NOT NULL,
                    source          text        NOT NULL,
                    page            integer     NOT NULL,
                    unit_id         text        NOT NULL,
                    section         text,
                    pep_type        text,
                    status          text,
                    python_version  text,
                    created_year    integer,
                    char_start      integer     NOT NULL,
                    char_end        integer     NOT NULL,
                    n_chars         integer     NOT NULL,
                    text            text        NOT NULL,
                    content_hash    text        NOT NULL,
                    model           text        NOT NULL,
                    metadata        jsonb       NOT NULL,
                    embedding       vector({self.dimensions}) NOT NULL,
                    ingested_at     timestamptz NOT NULL,
                    PRIMARY KEY (strategy, chunk_id)
                )""")
            cur.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_strat_type ON {TABLE} (strategy, pep_type)")
            cur.execute(f"CREATE INDEX IF NOT EXISTS {TABLE}_strat_doc ON {TABLE} (strategy, document_id)")
            # Column dimension must match the model.
            cur.execute("""SELECT atttypmod FROM pg_attribute
                           WHERE attrelid = %s::regclass AND attname = 'embedding'""", (TABLE,))
            dim = cur.fetchone()[0]
            if dim != self.dimensions:
                raise RuntimeError(f"table has vector({dim}) but model has {self.dimensions} dims")

    def existing_hashes(self, strategy: str) -> dict[str, tuple[str, str]]:
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT chunk_id, content_hash, model FROM {TABLE} WHERE strategy=%s", (strategy,))
            return {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]],
               model: str = "", replace_documents: bool = True) -> dict[str, int]:
        """Insert/update by stable (strategy, chunk_id); delete obsolete chunks.

        ``vectors[i]`` may be None for a chunk whose content_hash is unchanged
        (then the row is left untouched, no re-embedding). When
        ``replace_documents`` is True, rows of the same strategy and document that
        are not in ``chunks`` anymore are deleted (document changed / shrank).
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk_id in batch")
        now = datetime.now(timezone.utc)
        stats = {"inserted_or_updated": 0, "unchanged": 0, "deleted": 0}
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                for c, v in zip(chunks, vectors):
                    if v is None:
                        stats["unchanged"] += 1
                        continue
                    if len(v) != self.dimensions:
                        raise ValueError(f"vector for {c.chunk_id} has {len(v)} dims")
                    m = c.metadata
                    cur.execute(f"""
                        INSERT INTO {TABLE} (strategy, chunk_id, document_id, source, page, unit_id, section,
                            pep_type, status, python_version, created_year, char_start, char_end, n_chars,
                            text, content_hash, model, metadata, embedding, ingested_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                            document_id=EXCLUDED.document_id, source=EXCLUDED.source, page=EXCLUDED.page,
                            unit_id=EXCLUDED.unit_id, section=EXCLUDED.section, pep_type=EXCLUDED.pep_type,
                            status=EXCLUDED.status, python_version=EXCLUDED.python_version,
                            created_year=EXCLUDED.created_year, char_start=EXCLUDED.char_start,
                            char_end=EXCLUDED.char_end, n_chars=EXCLUDED.n_chars, text=EXCLUDED.text,
                            content_hash=EXCLUDED.content_hash, model=EXCLUDED.model,
                            metadata=EXCLUDED.metadata, embedding=EXCLUDED.embedding,
                            ingested_at=EXCLUDED.ingested_at""",
                        (strategy, c.chunk_id, c.document_id, c.source, c.page, m["unit_id"], m.get("section"),
                         m.get("pep_type"), m.get("status"), m.get("python_version"), m.get("created_year"),
                         m["char_start"], m["char_end"], m["n_chars"], c.text, m["content_hash"], model,
                         json.dumps(m, ensure_ascii=False), np.asarray(v, dtype=np.float32), now))
                    stats["inserted_or_updated"] += 1
                if replace_documents:
                    docs = sorted({c.document_id for c in chunks})
                    cur.execute(f"""DELETE FROM {TABLE} WHERE strategy=%s AND document_id = ANY(%s)
                                    AND NOT (chunk_id = ANY(%s))""", (strategy, docs, ids))
                    stats["deleted"] = cur.rowcount
        return stats

    def count(self, strategy: str | None = None) -> int:
        with self.conn.cursor() as cur:
            if strategy:
                cur.execute(f"SELECT count(*) FROM {TABLE} WHERE strategy=%s", (strategy,))
            else:
                cur.execute(f"SELECT count(*) FROM {TABLE}")
            return cur.fetchone()[0]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Exact (sequential-scan) cosine search; filters applied in SQL WHERE before ranking."""
        where, params = ["strategy = %s"], [strategy]
        for k, v in (filters or {}).items():
            if k not in FILTERABLE:
                raise ValueError(f"filter key {k!r} not allowed; allowed: {sorted(FILTERABLE)}")
            where.append(f"{k} = %s")
            params.append(v)
        qv = np.asarray(query_vector, dtype=np.float32)
        if qv.shape != (self.dimensions,):
            raise ValueError("query vector dimension mismatch")
        sql = f"""SELECT chunk_id, document_id, source, page, unit_id, section, pep_type, status,
                         python_version, created_year, char_start, char_end, text,
                         1 - (embedding <=> %s) AS score
                  FROM {TABLE} WHERE {' AND '.join(where)}
                  ORDER BY embedding <=> %s, chunk_id LIMIT %s"""
        with self.conn.cursor() as cur:
            cur.execute(sql, [qv, *params, qv, top_k])
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r["score"] = round(float(r["score"]), 6)
        return rows

    def close(self) -> None:
        self.conn.close()
