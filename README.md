# DataLens Q&A

A small AI-powered web application for asking analytical questions across uploaded CSV and Excel files. It uses DuckDB for deterministic analysis and a custom LangGraph workflow with a Groq-hosted open model for natural-language-to-SQL planning.

## Tech stack

| Layer | Technology |
| --- | --- |
| Web API | FastAPI and Uvicorn |
| Agent orchestration | LangGraph with custom nodes and routing |
| LLM integration | LangChain `ChatGroq` |
| Default model | `openai/gpt-oss-120b` on Groq |
| Data processing | pandas, OpenPyXL, and xlrd |
| Analytical database | DuckDB |
| SQL validation | SQLGlot |
| Frontend | HTML, CSS, JavaScript, and Chart.js |
| Packaging | `pyproject.toml`, Docker, and Docker Compose |

## What it supports

- Multiple `.csv`, `.xlsx`, and `.xls` files in one session, including every Excel sheet
- Cross-file SQL joins using deterministic join hints based on column names and sampled value overlap
- Totals, averages, filters, comparisons, and trends
- Guarded, read-only SQL with an allow-list of uploaded tables and an enforced result cap
- Automatic bar/line chart suggestions for suitable results
- A custom, function-based LangGraph agent with injected tool arguments, tool-specific routing, output post-processing, and bounded SQL retries

## Run with Docker (recommended)

1. Copy `.env.example` to `.env` and set a [Groq API key](https://console.groq.com/keys).
2. Start the application:

   ```bash
   docker compose up --build
   ```

3. Open <http://localhost:8000>.

Uploaded session data is stored in the `session-data` Docker volume. Stop with `docker compose down`; add `-v` only if you also want to delete uploaded data.

## Run locally

Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
# edit .env and set GROQ_API_KEY
uvicorn app.main:app --reload
```

The UI is at <http://localhost:8000>, OpenAPI docs at <http://localhost:8000/docs>, and health check at <http://localhost:8000/api/health>.

## Configuration

All non-secret application configuration lives in [`config.json`](config.json): model, upload limits, row limits, agent step/retry bounds, and join-hint threshold. Secrets stay in environment variables. Set `CONFIG_PATH` to use a different JSON file.

The default model is `openai/gpt-oss-120b` through `ChatGroq`. Change `model.name` in `config.json` if that model is unavailable for your Groq account.

## Deployment

### Recommended: Render with Docker

The current architecture stores a DuckDB database and metadata under `data/sessions` for each upload session. A container platform with a stable filesystem is therefore a better fit than a serverless function platform.

1. Initialize this directory as a Git repository and push it to GitHub or GitLab.
2. In Render, create a **Web Service** from the repository and choose the **Docker** runtime.
3. Add these environment variables:

   ```text
   GROQ_API_KEY=<your Groq API key>
   CONFIG_PATH=/app/config.json
   PORT=8000
   ```

4. Set the health-check path to `/api/health` and deploy.
5. For a short assignment demo, the service can use its default ephemeral filesystem. Uploaded sessions will be lost whenever the service restarts or redeploys.
6. For durable sessions, attach a persistent disk at `/app/data/sessions`. Render persistent disks are a paid feature and restrict the service to one instance, which is acceptable for this prototype.

Render supports Docker services and persistent disks: [Docker on Render](https://render.com/docs/docker) and [Persistent Disks](https://render.com/docs/disks).

### Can this run on Vercel?

Vercel supports FastAPI, but this application should **not be deployed there unchanged**:

- Vercel Functions have a read-only filesystem with only temporary `/tmp` scratch space. The upload request and later query request are not guaranteed to use the same function instance, so a session DuckDB file can disappear between requests.
- Function request and response payloads are limited to 4.5 MB, while this prototype permits files up to 25 MB.
- The current frontend is served by FastAPI, whereas Vercel recommends placing static assets in `public/`.

To make Vercel suitable, upload files directly to durable object storage such as Vercel Blob or S3, store session metadata in an external database, and reconstruct/download the DuckDB database into `/tmp` for each query—or replace local DuckDB persistence with an external analytical database. The frontend could then be hosted on Vercel while the existing Dockerized API runs on Render.

See the official [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [Vercel runtime filesystem](https://vercel.com/docs/functions/runtimes), and [Vercel Function limits](https://vercel.com/docs/functions/limitations) documentation.

## Architecture

```text
Browser → FastAPI dependency functions → ingestion → DuckDB + schema metadata
                                      → custom LangGraph agent_node
                                            ↓ route + inject args
                                      schema_tool / sql_tool
                                            ↓ process output
                                      retry / answer → chart rule → Browser
```

LangGraph's prebuilt ReAct agent is intentionally not used. The graph explicitly routes by tool name and processed tool outcome. The model sees tool outputs, while trusted values such as the session ID, settings, and schema registry are injected into hidden tool arguments by the router rather than generated by the model. Application business logic is function-based; classes are retained only for typed schemas, settings, state, and exceptions.

The main “delta” beyond an LLM wrapper is the deterministic data layer: normalized identifiers, profiling, cross-file join hints, AST-based SQL validation, table allow-listing, hard limits, and rule-based chart validation.

## API

- `POST /api/upload_file` — multipart upload using repeated `files` fields
- `POST /api/sessions/{session_id}/query` — JSON body: `{"question": "..."}`
- `GET /api/health`

## Tests

```bash
pytest
ruff check .
```

Tests cover identifier normalization, join inference, chart selection, agent routing, tool-output processing, and rejection of unsafe SQL. A live Groq call is deliberately excluded from the unit suite.

## Known prototype limits

- Sessions are local files and have no authentication or automatic expiry.
- Join hints are heuristic; ambiguous real-world keys may still need explicit user clarification.
- The chart layer intentionally supports only bar, line, and pie-ready response contracts.
- Very large files should be streamed to Parquet rather than loaded through pandas.

See [`WRITEUP.md`](WRITEUP.md) for the requested short approach note.
