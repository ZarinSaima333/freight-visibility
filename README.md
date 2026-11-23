# Freight Visibility

A local freight dashboard for reviewing delivery performance, investigating individual shipments, and returning data issues to operations. It seeds PostgreSQL from the supplied CSV on the first startup against an empty shipment table.

## Run locally

Use Python 3.11+, Node.js 20+, and PostgreSQL. Start your locally installed PostgreSQL server, then create an empty database with a role that can create tables in its public schema.

```bash
createdb freight_visibility
```

If your PostgreSQL binaries are outside `PATH`, use the executable from your installation. For example, an EnterpriseDB PostgreSQL 18 installation on macOS typically provides `/Library/PostgreSQL/18/bin/createdb`. If your installation created a password-protected `postgres` role, run `createdb -h localhost -U postgres freight_visibility` and use the matching connection URL below.

From the repository root:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Set `DATABASE_URL` in `.env` before starting Uvicorn. The example `postgresql:///freight_visibility` uses the local socket and your current OS role. For TCP, use `postgresql://USER:PASSWORD@localhost:5432/freight_visibility` with the password URL-encoded. For Neon or Supabase, create an empty PostgreSQL database and copy its PostgreSQL connection string, including its SSL options, into the same variable. The startup process runs `db/init.sql` and imports the seed automatically. No containers are needed.

In a second terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open [the dashboard](http://localhost:5173) or [the API docs](http://127.0.0.1:8000/docs). Vite proxies `/api` to FastAPI. Run `npm run build` from `frontend` for a production frontend bundle.

### CLI and tests

With the virtual environment activated and `.env` configured, run from the repository root:

```bash
python -m backend.cli
python -m backend.cli --grace 2
python -m backend.cli path/to/replacement.csv --mode replace
python -m pytest -q
```

The CLI with no CSV initializes the database if needed and prints metrics for the active snapshot. Passing a CSV imports it. Tests exercise cleaning and the query validator without a live database or Gemini key.

## Architecture

```text
Seed CSV, upload CSV or CLI
    -> pandas normalization, deterministic deduplication and validation
    -> PostgreSQL transaction
         -> upload_batches and shipments_raw preserve incoming batches
         -> removed_duplicates links kept and dropped versions
         -> shipments holds the active snapshot, quality flags and metric eligibility
    -> FastAPI parameterized queries
    -> React dashboard, shipment details, data quality and CSV export

Question -> Gemini or mock -> parsed and validated SQL
         -> PostgreSQL read-only transaction -> results
         -> Gemini or local summary -> answer, SQL and result table
```

Replace swaps the active snapshot and retains earlier source batches. Append applies the same ranking to incoming and active source versions. Delivered wins first, then the row with the most populated fields. Ties favor the newest batch and then the earliest source row within that batch. Uploads are UTF-8 CSV files up to 10 MB. The database transaction serializes competing uploads and keeps the raw audit and active view consistent.

## Data quality and metric assumptions

| Source issue | Treatment | Seed |
| --- | --- | ---: |
| Whitespace in fields | Trim and log the count of changed fields | 6 |
| Port casing and Chattogram aliases | Uppercase ports and map `CHATTOGRAM` and `CGP` to `BDCGP` | 12 casing changes, 12 alias mappings |
| Exact duplicates | Keep one normalized version and audit the dropped rows | 6 dropped |
| Conflicting duplicates | Keep the preferred row, retain both original versions, flag a warning | 5 conflicting rows dropped |
| Unambiguous D/M/Y fallback | Parse when the first number exceeds 12 and flag a warning | 28 shipments |
| Missing consignee | Display Unknown and flag a warning | 7 shipments |
| Invalid or out-of-window dates, reversed dates, status/ATA inconsistencies, suspect delays | Flag errors and exclude affected deliveries from timing metrics | 24 Delivered excluded |
| Negative, zero, implausibly high, missing or invalid weight | Flag an error, keep original data and clear the eligible weight | 6 weights excluded |

Dates use M/D/YYYY where valid and D-Mon-YY for month-name values. The allowed window is December 2025 through December 2026. Delays above 60 days or below −30 days are flagged. Delivered rows also need both ETA and ATA. In Transit rows with ATA are flagged and stay outside delivery metrics. Missing or malformed required date values receive specific flags. Unrecognized statuses and malformed nonblank volumes are flagged for review.

- **On-time percentage** uses Delivered rows with reliable ETA and ATA. On time means ATA ≤ ETA + grace. The dashboard supports 0–3 grace days. Average delay uses the same valid deliveries and retains negative values for early arrivals.
- **Total weight** sums eligible weights in kilograms and converts the result to metric tonnes. Weight errors leave timing eligibility intact.
- **Shipment and lane counts** include every deduplicated shipment. A trade lane is the origin port followed by the destination port.
- **Data-quality counts** use each shipment’s highest severity in the banner. One shipment can appear under multiple rules. The operations export includes original source columns and alternate conflicting versions. Correct the values at source and export a shipment CSV with the standard input headers for re-upload.

### Presentation numbers

| Metric | Seed result |
| --- | ---: |
| Raw rows / duplicates removed / unique shipments | 511 / 11 / **500** |
| On time at zero grace days | **57.6%** |
| Valid deliveries / Delivered rows excluded | **434 / 24** |
| On time at one / two grace days | 62.9% / 70.3% |
| Eligible total weight / excluded weights | **6,626.518 t / 6** |
| Chattogram → Valencia (`BDCGP → ESVLC`) | **77** |
| Chattogram → Rotterdam (`BDCGP → NLRTM`) | **73** |
| Chattogram → Hamburg (`BDCGP → DEHAM`) | **55** |

For the demo, change the grace period to two days, open a delayed shipment, and then open a flagged shipment from Data Quality to show the original values. Finish with the Rotterdam question and expand **SQL used**.

## Ask the Data

Set `GEMINI_API_KEY` in your server environment or gitignored `.env`. The code default is `gemini-2.5-flash`. Google returned a model availability error for that default with the supplied key. Use the override verified during the assessment:

```dotenv
GEMINI_MODEL=gemini-3.1-flash-lite
```

Restart the backend after changing its environment. With a blank key, **Mock mode** supports the four example buttons, the shipper with the most late deliveries, and queries about flagged shipments. Gemini mode accepts free-form questions and optional prior questions. When Gemini cannot generate SQL, supported questions use the same local SQL templates.

The SQL generation call sends schema, metric definitions, the question, and examples. The PostgreSQL AST validator accepts one SELECT with ordinary expressions and optional nonrecursive CTEs. It limits relation access to the active shipment table, qualifies allowed functions, rejects writes and locks, and caps output at 100 rows. The execution transaction is read-only with a five-second statement timeout. It uses `READONLY_DATABASE_URL` when configured and otherwise applies the same read-only transaction to `DATABASE_URL`. For a dedicated login, grant it `USAGE` on schema `public` and `SELECT` on `public.shipments` after the first startup.

Gemini can correct one rejected query using the validation or database error. The answer call receives the bounded result and the question. The results table and SQL are returned with the answer. A local summary is available if the answer call fails.

## What I would build in two more days

Add authentication and role-based uploads, an upload-history screen with batch comparisons, scheduled reports, and automatic email of the flagged-rows file to operations. Expand carrier scorecards with trends, add alerts for at-risk shipments, and prototype a delay prediction model with a time-based holdout and a simple baseline.
