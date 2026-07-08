import os
import sqlite3
import sys
import pandas as pd
import numpy as np

# Prevent UnicodeEncodeError on Windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def generate_report(db_path: str, output_csv: str):
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return

    print("Step 1: Connecting to database and loading SCADA data...")
    conn = sqlite3.connect(db_path)
    query = "SELECT PointName, Value, Timestamp FROM C_SCADA_DataArchive"
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading database: {e}")
        conn.close()
        return
    conn.close()

    if df.empty:
        print("No data found in C_SCADA_DataArchive.")
        return

    print("Step 2: Processing and cleaning timestamps...")
    # Convert types
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')

    # Round to nearest 30min
    df['Timestamp_Rounded'] = df['Timestamp'].dt.round('30min')
    
    # Calculate offset to keep the closest record in case of duplicates
    df['Minute_Offset'] = (df['Timestamp'] - df['Timestamp_Rounded']).dt.total_seconds().abs()
    df = df.sort_values(by=['Timestamp_Rounded', 'Minute_Offset'])
    df = df.drop_duplicates(subset=['PointName', 'Timestamp_Rounded'], keep='first')

    print("Step 3: Creating 30-minute time grid and pivoting data...")
    # Generate full time grid (June 2026: 30 days * 48 intervals = 1440 rows)
    all_time_grid = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-30 23:30:00", freq="30min")

    # Pivot table: Index is time, Columns are PointNames, Values are Values
    pivot_df = df.pivot(index='Timestamp_Rounded', columns='PointName', values='Value')
    
    # Reindex to force all 1440 half-hour time slots to exist
    report_df = pivot_df.reindex(all_time_grid)
    report_df.index.name = 'Timestamp'

    # Save to CSV
    # Ensure target folder exists
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    report_df.to_csv(output_csv, encoding='utf-8-sig') # utf-8-sig ensures Excel opens Chinese/symbols correctly
    print(f"✨ Success! Full report exported to: {output_csv}")

    # Step 4: Generate a preview of the first day (June 1st) in the terminal
    print("\n" + "="*95)
    print("                 SCADA 報表數據預覽 (2026-06-01 前半天)")
    print("                 說明: 空白處(NaN) 代表該時間點資料漏抓/缺失")
    print("="*95)
    
    # Select first day (48 intervals, let's show first 24 intervals: 00:00 to 11:30)
    preview_df = report_df.iloc[:24].copy()
    
    # Select first 4 columns for clean terminal display, plus a count of missing points in each row
    cols_to_show = list(preview_df.columns[:4])
    preview_df['Missing_Points_Count'] = preview_df.isna().sum(axis=1)
    
    # Format and print
    col_width_name = 18
    header_format = "{:<16} | " + " | ".join([f"{{:<{col_width_name}}}" for _ in cols_to_show]) + " | {:<10}"
    row_format = "{:<16} | " + " | ".join([f"{{:<{col_width_name}}}" for _ in cols_to_show]) + " | {:<10}"
    
    # Clean column names for header display
    header_names = [name[:col_width_name] for name in cols_to_show]
    print(header_format.format("Timestamp", *header_names, "Missing/16"))
    print("-"*95)
    
    for ts, row in preview_df.iterrows():
        ts_str = ts.strftime('%Y-%m-%d %H:%M')
        values = []
        for col in cols_to_show:
            val = row[col]
            values.append("NaN" if pd.isna(val) else f"{val:.3f}")
        missing_cnt = int(row['Missing_Points_Count'])
        
        # Color warning if any points are missing in this row
        warn_str = f"{missing_cnt} points" if missing_cnt > 0 else "0 (OK)"
        print(row_format.format(ts_str, *values, warn_str))
    print("="*95)
    print(f"提示: 您現在可以直接用 Excel 開啟檔案: {os.path.abspath(output_csv)}")
    print("="*95 + "\n")

if __name__ == "__main__":
    generate_report("data/sif_sqlite.db", "data/scada_missing_report.csv")
