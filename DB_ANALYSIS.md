# Database Case Analysis: Slow Affiliate Count Query

## The problem

The back office team reports that checking how many affiliates a client has is
very slow. Investigation with the dev team produced these clues:

- Database CPU usage spikes during that time.
- Dashboard / application resources are normal (no spikes anywhere).
- The backend issues this query:

```sql
SELECT count(affiliates) FROM client WHERE client_id = 'this_is_client_id';
```

### Table schema (`client`)

| Column     | Type         | Nullable | Notes        |
|------------|--------------|----------|--------------|
| id         | integer      | NOT NULL | Primary Key  |
| affiliates | varchar(250) | NULL     |              |
| client_id  | varchar(250) | NULL     |              |

Indexes: only the Primary Key on `id`. No index on `client_id`.
No foreign keys, no unique constraints.

## Root cause

The query filters on `client_id`, but the only index is the Primary Key on `id`.
Because `client_id` is **not indexed**, PostgreSQL must perform a **Sequential
Scan** — it reads every row in the `client` table and compares `client_id` one by
one.

This explains all three clues:

- **Database CPU spikes** — scanning the entire table is CPU-intensive, and it
  scales linearly with table size.
- **Application/dashboard resources are normal** — the bottleneck is entirely on
  the database side, not the app.
- **Data is slow to show** — the full scan takes longer as the table grows.

## Reproduction and proof

Reproduced on PostgreSQL 16 with the exact schema from the case and 100,000 rows
of synthetic data:

```sql
CREATE TABLE client (
    id SERIAL PRIMARY KEY,
    affiliates VARCHAR(250),
    client_id  VARCHAR(250)
);

INSERT INTO client (affiliates, client_id)
SELECT
    md5(random()::text),
    'client_' || floor(random()*1000)
FROM generate_series(1,100000);
```

### Before — Sequential Scan

```sql
EXPLAIN ANALYZE
SELECT count(affiliates) FROM client WHERE client_id = 'client_500';
```

```
Aggregate  (cost=2185.25..2185.26 rows=1 width=8) (actual time=9.423..9.425 rows=1 loops=1)
  ->  Seq Scan on client  (cost=0.00..2185.00 rows=99 width=33) (actual time=0.081..9.403 rows=97 loops=1)
        Filter: ((client_id)::text = 'client_500'::text)
        Rows Removed by Filter: 99903
Planning Time: 0.601 ms
Execution Time: 9.467 ms
```

Key evidence: `Rows Removed by Filter: 99903`. PostgreSQL read all 100,000 rows
and discarded 99,903 just to return 97 matches. This full-table read is the source
of the CPU spike.

### Fix — add an index on the filtered column

```sql
CREATE INDEX idx_client_client_id ON client (client_id);
ANALYZE client;   -- refresh planner statistics so it picks the new index
```

### After — Bitmap Index Scan

```sql
EXPLAIN ANALYZE
SELECT count(affiliates) FROM client WHERE client_id = 'client_500';
```

```
Aggregate  (cost=295.70..295.71 rows=1 width=8) (actual time=0.316..0.317 rows=1 loops=1)
  ->  Bitmap Heap Scan on client  (cost=5.06..295.45 rows=99 width=33) (actual time=0.111..0.283 rows=97 loops=1)
        Recheck Cond: ((client_id)::text = 'client_500'::text)
        Heap Blocks: exact=94
        ->  Bitmap Index Scan on idx_client_client_id  (cost=0.00..5.04 rows=99 width=0) (actual time=0.085..0.085 rows=97 loops=1)
              Index Cond: ((client_id)::text = 'client_500'::text)
Planning Time: 0.568 ms
Execution Time: 0.478 ms
```

**Result: 9.467 ms -> 0.478 ms, roughly a 20x improvement.**

### Notes on the plan

- **Why "Bitmap Index Scan" and not a plain "Index Scan"?** The value `client_500`
  matches 97 rows scattered across 94 heap blocks. For many matches spread across
  many pages, the planner prefers a bitmap scan (collect all matching locations
  into a bitmap first, then fetch) over a plain index scan. This is the planner's
  normal, optimal choice — not a problem. For a highly selective filter (1–2 rows)
  it would typically use a plain Index Scan.

- **Scale matters.** At 100,000 rows the Seq Scan is still only ~9 ms, but a Seq
  Scan grows **linearly**: at 10 million rows it becomes hundreds of ms to seconds
  and the CPU spike is severe, while the Index Scan stays close to constant. This
  is why the issue is painful in production with a large table even though it looks
  mild at test scale.

## Resolution summary

### Level 1 — Quick win (immediate relief)

```sql
CREATE INDEX idx_client_client_id ON client (client_id);
```

Converts the Sequential Scan into an index-based scan; the CPU spike disappears
because the database no longer reads the whole table.

### Level 2 — Fix the data model (the deeper issue)

Two design smells are worth flagging:

1. `count(affiliates)` is likely **semantically wrong**. `affiliates` is a
   `varchar(250)`, i.e. one string column per client row — not a one-to-many
   relation. `count(affiliates)` counts how many matching rows have a non-null
   `affiliates` value, not the actual number of affiliates.

2. The `client` table has both a PK `id` and a separate `client_id` column, which
   suggests affiliates should be their own table referencing the client.

A proper model:

```sql
CREATE TABLE affiliate (
    id         serial PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES client(id),
    name       varchar(250)
);
CREATE INDEX idx_affiliate_client_id ON affiliate (client_id);
```

Then the query becomes both correct and fast:

```sql
SELECT count(*) FROM affiliate WHERE client_id = <client_id>;
```

## Conclusion

The immediate cause is a missing index on `client_id`, forcing a full-table
Sequential Scan that spikes database CPU (proven: 99,903 rows removed by filter).
The quick fix is to add that index, which cut execution time ~20x in reproduction.
The correct long-term fix is to model affiliates as a separate, indexed table with
a foreign key, which also makes the count semantically correct.
