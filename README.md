# ERP Data Bridge

[English](#english) | [中文](#中文)

## English

Python CLI for moving tables and data from one SQL Server database to another. The code is adapter-based so SQLite or other targets can be added later without rewriting the migration flow.

### Setup

Install Microsoft ODBC Driver for SQL Server first, then install Python packages:

```powershell
pip install -r requirements.txt
```

Copy the sample config and edit the connection values:

```powershell
Copy-Item config.example.yaml config.yaml
```

### Run

Run a live migration:

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

### Config

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

### Current Scope

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

## 中文

ERP Data Bridge 是一個 Python CLI 工具，用來把 SQL Server 資料庫的資料表結構與資料搬到另一個 SQL Server 資料庫。程式採用 adapter 架構，之後可以擴充 SQLite 或其他資料庫目標，不需要重寫整個搬移流程。

### 安裝

請先安裝 Microsoft ODBC Driver for SQL Server，例如 `ODBC Driver 17 for SQL Server`，再安裝 Python 套件：

```powershell
pip install -r requirements.txt
```

複製設定檔範本：

```powershell
Copy-Item config.example.yaml config.yaml
```

然後修改 `config.yaml` 裡面的來源與目標資料庫連線資訊。

### 執行

正式搬移：

```powershell
python -m db_migrator --config config.yaml
```

只預覽，不修改目標資料庫：

```powershell
python -m db_migrator --config config.yaml --dry-run
```

關閉彩色輸出：

```powershell
$env:NO_COLOR = "1"
```

### 設定檔

`options.tables` 可以指定要搬的資料表：

```yaml
options:
  tables:
    - dbo.Customers
    - dbo.Orders
```

如果要搬全部 user tables，設定成空陣列：

```yaml
options:
  tables: []
```

建議不要把密碼直接放進 `config.yaml`，可以改用環境變數：

```yaml
source:
  username: "sa"
  password_env: "SOURCE_DB_PASSWORD"

target:
  username: "sa"
  password_env: "TARGET_DB_PASSWORD"
```

PowerShell 設定方式：

```powershell
$env:SOURCE_DB_PASSWORD = "來源密碼"
$env:TARGET_DB_PASSWORD = "目標密碼"
```

常用選項：

```yaml
options:
  batch_size: 5000
  if_exists: recreate
  include_data: true
  include_primary_keys: true
  include_indexes: true
  preserve_identity: true
  verify_row_counts: true
```

`if_exists` 說明：

- `recreate`：目標表存在時先刪除再重建，然後搬資料。
- `truncate`：目標表存在時清空資料，保留原本結構，然後搬資料。
- `skip`：目標表存在時跳過，不搬資料。

正式搬移前建議先跑：

```powershell
python -m db_migrator --config config.yaml --dry-run
```

確認資料表數量、筆數與設定沒問題後，再執行正式搬移。

### 程式架構

整體流程：

```text
CLI
  ↓
Config Loader
  ↓
Migrator
  ↓
Source Adapter ── reads schema/data from source database
  ↓
Target Adapter ── creates tables/indexes and inserts data
```

目前實作：

```text
MSSQL Source → MSSQL Target
```

未來擴充 SQLite 時，可以新增 `SQLiteTarget`，讓流程變成：

```text
MSSQL Source → SQLite Target
```

核心設計重點：

- `Migrator` 只負責流程控制，不直接寫 SQL Server 細節。
- `DatabaseSource` 負責讀取來源資料表、schema、筆數與資料列。
- `DatabaseTarget` 負責建立目標資料表、寫入資料、建立索引與驗證筆數。
- SQL Server 細節集中在 `adapters/mssql.py`，之後擴充其他資料庫時比較不會影響主流程。

### 檔案說明

```text
db_migrator/
  __main__.py              python -m db_migrator 的入口
  cli.py                   CLI 參數解析、log 初始化、啟動 Migrator
  config.py                讀取 YAML 設定檔，支援 password_env
  console.py               彩色 CLI 輸出與 log formatter
  factory.py               依照 config 建立 source/target adapter
  migrator.py              搬移主流程，包含 dry-run、資料搬移、row count 驗證、建立索引
  adapters/
    base.py                Source/Target adapter 介面與 schema 資料模型
    mssql.py               SQL Server source/target 實作
```

其他檔案：

```text
config.example.yaml        設定檔範本，不含真實密碼
requirements.txt           Python 套件需求
.gitignore                 排除真實 config、__pycache__、pyc 檔
README.md                  專案說明文件
```

### 目前支援

- SQL Server 來源
- SQL Server 目標
- 掃描 user tables
- 建立資料表
- 常見 SQL Server 型別轉換
- primary key
- clustered / nonclustered primary key
- clustered / nonclustered index
- unique index
- included columns
- descending key
- filtered index
- identity 欄位與 `IDENTITY_INSERT`
- 批次搬移資料
- 每張表進度條
- 彩色 CLI
- dry-run 預覽
- 搬完後 row count 驗證
- `password_env` 環境變數密碼

### 尚未支援

- foreign key
- view
- stored procedure
- function
- trigger
- computed column 定義
- SQLite target

### 注意事項

如果 `if_exists: recreate`，目標資料庫裡同名資料表會被刪除後重建。正式搬移前請務必先執行 `--dry-run` 確認。

真實連線設定請放在 `config.yaml` 或 `config_*.yaml`，這些檔案已被 `.gitignore` 排除，不會被 commit。請只把 `config.example.yaml` 上傳到 GitHub。
