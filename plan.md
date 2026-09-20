# Full architecture plan — NL querying over CSV/Excel with cross-file joins and visualization

## 1. Goals recap

- Upload one or more CSV/Excel files (multi-sheet aware)
- Ask questions in natural language, including questions that span multiple files
- Get back tabular answers, charts, and diagrams
- Reliable, sandboxed, debuggable — not a black box agent wandering freely

## 2. System components

```
Frontend (upload + chat + render)
   │
   ▼
Ingestion Service ── parses files, infers schema, loads into DuckDB, computes join hints
   │
   ▼
Schema Registry ── metadata store (not the data itself)
   │
   ▼
Orchestrator ── owns the agent loop, iteration limits, error handling
   │
   ├── schema_tool ── list_tables / get_schema / sample_rows
   ├── query_tool ── run_sql
   ├── visualize_tool ── render_chart / render_diagram
   └── clarify_tool ── ask_clarification   (optional, human-in-loop)
   │
   ▼
Response Assembler ── NL answer + table + chart/diagram spec → frontend
```

## 3. Ingestion pipeline

1. On upload, detect file type (`.csv`, `.xlsx`, `.xls`).
2. Parse with pandas (`read_csv` / `read_excel`, `sheet_name=None` to get all sheets).
3. Type inference: let pandas infer, then coerce ambiguous columns (e.g. date-like strings) explicitly — don't trust pandas' default dtype guess blindly for dates/currency.
4. Load each sheet as a DuckDB table: `file1_sheet1`, `file2_orders`, etc. Use clean, model-friendly table names (strip spaces/special chars).
5. For large files, write to Parquet first, then `CREATE TABLE ... AS SELECT * FROM read_parquet(...)` — keeps DuckDB memory-efficient and lets you reload sessions cheaply.
6. Compute basic stats per column: null %, distinct count, min/max (numeric), sample values — store in the schema registry, not re-computed per query.

## 4. Schema registry

A lightweight metadata table (can literally be a DuckDB table itself, or JSON in your app DB):

```
table_name | column_name | dtype | sample_values | null_pct | source_file
```

Plus a **join-hint table**, computed once per upload batch:

- Column-name similarity (e.g. Levenshtein/embedding similarity between `customer_id` and `cust_id`)
- Value-overlap check: sample 100 values from each candidate column pair, check overlap ratio
- Store top candidate join pairs with a confidence score

This hint table is what makes cross-file querying *reliable* instead of the model guessing blindly — it's computed with plain code, not the LLM, so it's fast and deterministic.

## 5. The three (or four) tools

**`schema_tool`**

- `list_tables()` → table names + row counts + source file
- `get_schema(table)` → columns, types, samples
- `get_join_hints(table_a, table_b)` → candidate join keys with confidence

**`query_tool`**

- `run_sql(query)` → rows (capped, e.g. 500), row count, execution time, or structured error message
- Runs against a **read-only** DuckDB connection, per-session, with a query timeout (e.g. 5s) and automatic `LIMIT` injection if the model forgets one

**`visualize_tool`**

- `render_chart(spec)` → takes a Vega-Lite JSON spec (or a simplified schema you define: `{type, x, y, series, data_ref}`) — rendered client-side
- `render_diagram(spec)` → Mermaid syntax, mainly for `erDiagram`-style cross-file relationship views

**`clarify_tool`** *(optional but recommended once you see real ambiguous cases)*

- `ask_clarification(question, options?)` → stops the loop, surfaces the question to the user, resumes on their reply

## 6. Agent loop (orchestration — mostly your code, not model "vibes")

```
1. Inject schema registry + join hints into system prompt (or as first tool results)
2. User sends NL query
3. Loop (max N=5 iterations):
   a. Model reasons, picks a tool call
   b. Orchestrator executes tool, returns result (or structured error)
   c. If run_sql errors → feed error back, let model retry once or twice
   d. If model calls run_sql successfully → offer next step (visualize or answer)
   e. If model calls clarify_tool → break loop, wait for user
4. On loop exit (success or max iterations): assemble final response
5. If max iterations hit without success → return graceful fallback, not a hallucinated answer
```

Keep this loop as **plain code with hard limits**, not model-controlled recursion — this is exactly the "custom agent, not generic ReAct" distinction from before.

## 7. System prompt structure

- Role + task framing ("You answer questions about uploaded tabular data using SQL against DuckDB")
- Full schema registry (tables, columns, types, 2-3 sample rows each)
- Join hints, explicitly: "Table A and Table B likely join on X↔Y (confidence: high)"
- Tool-use instructions: always inspect schema before assuming column names; always use join hints before guessing; ask via `clarify_tool` if two candidate joins are similarly confident
- Output contract: after getting data, decide whether a chart adds value; if so, emit a `render_chart` call with a spec grounded in the actual result columns

## 8. Visualization logic

- After a successful query, a lightweight rule (in code, not the LLM) can pre-decide "chartable-ness": e.g. if result has 1 numeric + 1 categorical column and ≤50 rows → suggest bar chart; time column + numeric → line chart. Feed this hint to the model so it doesn't have to reason chart-type selection from scratch every time — it just confirms/adjusts.
- Model emits a **spec**, not code. Spec is validated (allowed chart types, field names must exist in the result set) before being handed to the frontend renderer. Never let the model emit raw JS.
- Diagram requests ("show me how these files relate") route straight to `render_diagram` using the join-hint table — mostly deterministic, model just picks which entities to include.

## 9. Guardrails

- DuckDB connection: read-only, per-session, statement timeout, row cap
- Reject non-`SELECT` SQL outright (no `DROP`/`DELETE`/`ATTACH` etc. — even though it's the model's own SQL, don't trust it)
- Max iterations per query (prevents infinite tool-call loops)
- Confidence threshold on join hints below which the agent must clarify rather than guess

## 10. Tech stack

| Layer             | Choice                                                                             |
| ----------------- | ---------------------------------------------------------------------------------- |
| Backend           | FastAPI                                                                            |
| Query engine      | DuckDB (embedded, per-session file or in-memory)                                   |
| Parsing           | pandas + openpyxl                                                                  |
| Model             | Claude, tool use / function calling                                                |
| Chart rendering   | Vega-Lite + vega-embed (frontend)                                                  |
| Diagram rendering | Mermaid                                                                            |
| Session state     | Redis or simple per-session file, mapping session → DuckDB file + schema registry |

## 11. Build order (suggested phases)

1. **Ingestion + schema registry** — get files reliably into DuckDB with correct types, no LLM involved yet
2. **Single-file NL→SQL** — schema_tool + query_tool only, one file at a time, validate accuracy before adding complexity
3. **Cross-file joins** — add join-hint computation + expose via schema_tool, test on deliberately messy column-name mismatches
4. **Visualization** — add visualize_tool once query accuracy is solid; don't build charts on top of a shaky query layer
5. **Clarification tool** — add once you've logged enough real ambiguous cases to know what "ambiguous" looks like in practice
6. **Guardrails hardening** — timeouts, row caps, read-only enforcement, iteration limits — do this before any real user data touches it, not after

---

Want me to write out the actual system prompt text and the tool JSON schemas next, or a working FastAPI + DuckDB ingestion endpoint to start from?
