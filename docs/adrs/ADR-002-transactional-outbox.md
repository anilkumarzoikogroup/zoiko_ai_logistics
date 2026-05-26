# ADR-002: Transactional Outbox for Reliable Kafka Publishing

**Status:** Accepted  
**Date:** 2025-09-05  
**Deciders:** Zoiko Engineering

---

## Context

Phase 2 services must publish Kafka events when they write business records to PostgreSQL.
The naive approach (write DB then publish to Kafka) has a fatal race condition: if the
process crashes between the DB commit and the Kafka publish, the event is lost.

## Decision

Use the **Transactional Outbox pattern**:

1. Business logic writes the domain record AND an `outbox` row in the **same DB transaction**.
2. A background `OutboxRelay` polls `WHERE published = FALSE`, publishes to Kafka, then
   marks `published = TRUE`.

The `outbox` table schema:
```sql
id            UUID PRIMARY KEY
tenant_id     UUID NOT NULL
topic         VARCHAR(128) NOT NULL
partition_key VARCHAR(128) NOT NULL
payload       JSONB NOT NULL
published     BOOLEAN DEFAULT FALSE
published_at  TIMESTAMPTZ
created_at    TIMESTAMPTZ DEFAULT NOW()
```

## Rationale

| Alternative | Rejected because |
|-------------|-----------------|
| Dual write (DB then Kafka) | Lost events on crash between the two writes |
| Saga choreography | Too complex for a 4-phase pipeline; hard to audit |
| Kafka transactions | Requires Kafka 2.5+ transactional API; DB is the source of truth |
| CDC (Debezium) | Operational complexity; additional infra component |

The outbox pattern requires only a standard PostgreSQL connection. The `OutboxRelay`
runs in-process in dev and as a sidecar in production.

## Consequences

- **At-least-once delivery:** If the relay crashes after publishing but before marking
  `published = TRUE`, the event is re-published. Consumers MUST be idempotent.
- **Append-only constraint:** The `outbox` table is append-only (no UPDATE/DELETE on
  rows, only the relay sets `published = TRUE`).
- **Dev simplification:** In dev/tests, `MockKafkaBroker` handles publish in-memory
  without the relay. The relay is only needed for production correctness.
