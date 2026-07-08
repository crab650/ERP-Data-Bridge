import os
import sqlite3
import sys
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def check_missing_data(db_path: str):
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    query = "SELECT point_id, PointName, Value, Timestamp FROM C_SCADA_DataArchive"
    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading database: {e}")
        conn.close()
        return
    conn.close()

    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')

    all_hours = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-30 23:30:00", freq="30min")
    total_hours = len(all_hours) # 1440 (30 days * 48 half-hours)

    results = []

    for (point_id, point_name), group in df.groupby(['point_id', 'PointName']):
        # --- 1. 嚴格對齊 (Strict) ---
        # 僅保留分鐘為 00 或 30 的資料
        strict_group = group[group['Timestamp'].dt.minute.isin([0, 30])].copy()
        strict_group = strict_group.drop_duplicates(subset=['Timestamp'])
        strict_aligned = strict_group.set_index('Timestamp').reindex(all_hours)
        strict_missing = strict_aligned['Value'].isna().sum()

        # --- 2. 就近對齊 (Nearest) ---
        # 將時間四捨五入到最接近的 30 分鐘
        nearest_group = group.copy()
        nearest_group['Timestamp_Rounded'] = nearest_group['Timestamp'].dt.round('30min')
        # 如果四捨五入後有重複，保留最接近 30 分鐘整點的
        nearest_group['Minute_Offset'] = (nearest_group['Timestamp'] - nearest_group['Timestamp_Rounded']).dt.total_seconds().abs()
        nearest_group = nearest_group.sort_values(by=['Timestamp_Rounded', 'Minute_Offset'])
        nearest_group = nearest_group.drop_duplicates(subset=['Timestamp_Rounded'], keep='first')
        
        nearest_aligned = nearest_group.set_index('Timestamp_Rounded').reindex(all_hours)
        nearest_missing = nearest_aligned['Value'].isna().sum()

        results.append({
            "point_id": point_id,
            "PointName": point_name,
            "Strict_Missing": strict_missing,
            "Strict_Rate": round((strict_missing / total_hours) * 100, 2),
            "Nearest_Missing": nearest_missing,
            "Nearest_Rate": round((nearest_missing / total_hours) * 100, 2),
        })

    result_df = pd.DataFrame(results).sort_values(by="Nearest_Rate", ascending=False)

    print("\n" + "="*95)
    print("                SCADA 點位缺失狀況對比報告 (2026-06 - 30分鐘頻率)")
    print("="*95)
    template = "{:<6} | {:<25} | {:<18} | {:<18} | {:<12}"
    print(template.format("ID", "Point Name", "Strict Miss (嚴格)", "Nearest Miss (就近)", "改善幅度"))
    print("-"*95)
    for idx, row in result_df.iterrows():
        improvement = row['Strict_Missing'] - row['Nearest_Missing']
        print(template.format(
            row['point_id'],
            row['PointName'][:25],
            f"{row['Strict_Missing']} 次 ({row['Strict_Rate']}%)",
            f"{row['Nearest_Missing']} 次 ({row['Nearest_Rate']}%)",
            f"+{improvement} 次" if improvement > 0 else "無差異"
        ))
    print("="*95)
    print(f"註: 應有總次數為 {total_hours} 次 (30天 × 每天48次)。")
    print("="*95 + "\n")

if __name__ == "__main__":
    check_missing_data("data/sif_sqlite.db")
