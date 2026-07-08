# ERP Data Bridge

Python CLI for copying SQL Server table schemas and data into another SQL Server database or into a local SQLite database.

## Setup

Install Microsoft ODBC Driver for SQL Server first, then install Python packages:

```powershell
pip install -r requirements.txt
```

Copy the sample config and edit the connection values:

```powershell
Copy-Item config.example.yaml config.yaml
```

Use environment variables for passwords instead of committing credentials:

```powershell
$env:SOURCE_DB_PASSWORD = "source_password"
$env:TARGET_DB_PASSWORD = "target_password"
```

## Run

Preview the migration without changing the target database:

```powershell
python -m db_migrator --config config.yaml --dry-run
```

Run a live migration:

```powershell
python -m db_migrator --config config.yaml
```

The CLI uses colored output when the terminal supports ANSI colors. To disable colors:

```powershell
$env:NO_COLOR = "1"
```

## Configuration

`source.type` currently supports:

- `mssql`

`target.type` currently supports:

- `mssql`
- `sqlite`

For a SQLite export, set the target like this:

```yaml
target:
  type: sqlite
  database: "data/export.sqlite"
```

`options.tables` accepts either full names like `dbo.Customers` or table names like `Customers`. An empty list migrates all user tables.

```yaml
options:
  tables:
    - dbo.Customers
    - dbo.Orders
```

`options.where` can limit copied source rows per table. Keys can be full table names or table names:

```yaml
options:
  where:
    dbo.C_SCADA_DataArchive: "Timestamp >= '2026-06-01' AND Timestamp < '2026-07-01'"
    Customers: "IsActive = 1"
```

The same `where` filter is used for source row counts, dry-run previews, data copy, and row-count verification.

`options.if_exists` controls what happens when the target table already exists:

- `recreate`: drop and recreate the target table, then copy data.
- `truncate`: keep the target schema, delete existing rows, then copy data.
- `skip`: leave existing tables alone and do not copy data.

Common options:

```yaml
options:
  tables: []
  batch_size: 5000
  if_exists: recreate
  include_data: true
  include_primary_keys: true
  include_indexes: true
  preserve_identity: true
  verify_row_counts: true
  where: {}
```

## SCADA Utilities

This repository also includes helper scripts for checking SCADA archive completeness after exporting data to SQLite.

```powershell
python .\check_missing_hours.py
```

`check_missing_hours.py` reads `data/sif_sqlite.db`, checks `C_SCADA_DataArchive`, and compares missing values across a 30-minute grid for June 2026.

```powershell
python .\generate_scada_report.py
```

`generate_scada_report.py` creates a pivot-style CSV report where each SCADA point is a column and each 30-minute timestamp is a row. Blank cells represent missing or invalid values.

`SCADA_Data_Imputation_Guide.md` documents the planned detection and imputation approach, including missing timestamp detection, NaN/null handling, linear interpolation, forward/backward fill, rolling means, and historical seasonal filling.

Database files and generated reports are intentionally ignored by Git. Keep real exports such as `*.db`, `*.sqlite`, and generated CSV files local.

## Current Scope

Implemented:

- SQL Server source
- SQL Server target
- SQLite target
- Table discovery
- Column type mapping for common SQL Server types
- Primary key creation
- Clustered/nonclustered primary key mode for SQL Server targets
- Clustered/nonclustered index creation for SQL Server targets
- Unique indexes, included columns, descending keys, and filtered indexes for SQL Server targets
- Basic SQLite table and index creation
- Identity column creation and `IDENTITY_INSERT` for SQL Server targets
- Batched data copy with progress bars
- Dry-run preview mode
- Row count verification after each copied table
- Per-table source filtering through `options.where`
- Passwords from environment variables via `password_env`

Not implemented yet:

- Foreign keys
- Views, stored procedures, functions, and triggers
- Computed column definitions
- Full cross-database type fidelity for every SQL Server-specific type

## Project Layout

```text
db_migrator/
  __main__.py              python -m db_migrator entry point
  cli.py                   CLI argument parsing and logging setup
  config.py                YAML config loader
  console.py               Colored CLI logging
  factory.py               Source/target adapter factory
  migrator.py              Migration workflow
  adapters/
    base.py                Adapter interfaces and schema models
    mssql.py               SQL Server source/target implementation
    sqlite.py              SQLite target implementation

check_missing_hours.py     SCADA missing-data comparison script
generate_scada_report.py   SCADA CSV report generator
config.example.yaml        Example config without real secrets
requirements.txt           Python package requirements
```

## Notes

Run `--dry-run` before a live migration, especially when using `if_exists: recreate`, because existing target tables can be dropped and recreated.

Do not commit real connection configs, database exports, or generated reports. `config.yaml`, `config_*.yaml`, `*.db`, `*.sqlite`, and generated CSV files are excluded through `.gitignore`.
