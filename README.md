# ERP Data Bridge

Python CLI for moving tables and data from one SQL Server database to another. The code is adapter-based so SQLite or other targets can be added later without rewriting the migration flow.

## Setup

Install Microsoft ODBC Driver for SQL Server first, then install Python packages:

```powershell
pip install -r requirements.txt
```

Copy the sample config and edit the connection values:

```powershell
Copy-Item config.example.yaml config.yaml
```

## Run

```powershell
python -m db_migrator --config config.yaml
```

Preview the migration without changing the target database:

```powershell
python -m db_migrator --config config.yaml --dry-run
```

The CLI uses colored output when the terminal supports ANSI colors. To disable colors:

```powershell
$env:NO_COLOR = "1"
```

## Config

`options.tables` accepts either full names like `dbo.Customers` or table names like `Customers`. An empty list migrates all user tables.

Use environment variables for passwords when possible:

```yaml
source:
  username: "sa"
  password_env: "SOURCE_DB_PASSWORD"
```

PowerShell example:

```powershell
$env:SOURCE_DB_PASSWORD = "source_password"
$env:TARGET_DB_PASSWORD = "target_password"
```

`options.if_exists`:

- `recreate`: drop and recreate the target table, then copy data.
- `truncate`: keep target schema, truncate data, then copy data.
- `skip`: leave existing tables alone and do not copy data.

## Current Scope

Implemented:

- SQL Server source
- SQL Server target
- Table discovery
- Column type mapping for common SQL Server types
- Primary key creation
- Clustered/nonclustered primary key mode
- Clustered/nonclustered index creation
- Unique indexes, included columns, descending keys, and filtered indexes
- Identity column creation and `IDENTITY_INSERT`
- Batched data copy with `pyodbc.fast_executemany`
- Per-table progress bars
- Colored CLI output
- Dry-run preview mode
- Row count verification after each copied table
- Passwords from environment variables via `password_env`

Not implemented yet:

- Foreign keys
- Views, stored procedures, triggers
- Computed column definitions
- SQLite target
