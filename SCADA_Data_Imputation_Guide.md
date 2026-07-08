# SCADA 資料缺失檢測與補值方案規劃 (SCADA Data Imputation Guide)

本文件針對 SCADA 歷史數據封存表 `C_SCADA_DataArchive` 中「點位每小時抓取一次，但存在缺失小時或 NaN 無效值」的問題，規劃完整的篩選方法與補值演算法方案。

---

## 一、 缺失資料的兩種類型

在 SCADA 系統中，資料缺失通常以下面兩種形式出現：

| 缺失類型 | 表現形式 | 產生原因 | 偵測方法 |
| :--- | :--- | :--- | :--- |
| **隱性缺失 (Missing Hours)** | 資料庫中**完全沒有**該點位在該小時的 Record（時間軸斷軌）。 | 網路斷線、收集程式當機、資料庫寫入失敗。 | 比對標準每小時時間軸，找出「不存在的 Timestamp」。 |
| **顯性缺失 (NaN / Null)** | 資料庫中有那一小時的 Record，但 `Value` 欄位為 `NaN`、`Null` 或非數字字串。 | 儀表故障、讀取異常、感測器回傳錯誤代碼（如 `-9999` 或 `NaN`）。 | 檢查 `Value IS NULL` 或使用 `pandas.isna()`。 |

---

## 二、 缺失值篩選與檢測方法

為了準確定位哪些點位在哪些時間點有缺失，建議使用 Python `pandas` 配合 `sqlite3` 進行**時間網格對齊**：

### 步驟 1：建立標準時間網格 (DateTime Grid)
定義需要分析的時間範圍（例如 2026 年 6 月全月共 720 個小時），生成完整的每小時時間序列：
```python
import pandas as pd

# 生成 6 月份完整的 720 個小時時間點
complete_timestamps = pd.date_range(
    start="2026-06-01 00:00:00", 
    end="2026-06-30 23:00:00", 
    freq="h"
)
```

### 步驟 2：點位資料展開與對齊 (Reindexing)
將資料庫中每個點位的歷史資料，與這個標準網格進行 `reindex` 對齊。此時：
* 沒抓到資料的時間點會自動填入 `NaN`（顯性化隱性缺失）。
* 原本就是無效值的資料會保持 `NaN`。

---

## 三、 補值 (Imputation) 演算法分析

SCADA 資料主要為工業感測器數據，不同物理特性的數據適用不同的補值演算法：

### 1. 線性插補 (Linear Interpolation)
* **公式原理**：利用缺失點前一個有效值 $y_0$（時間 $t_0$）與後一個有效值 $y_1$（時間 $t_1$），連成直線計算中間時間 $t$ 的值：
  $$y = y_0 + \frac{y_1 - y_0}{t_1 - t_0} \times (t - t_0)$$
* **適用場景**：**連續且緩慢變化的物理量**。例如：水溫、油溫、槽體液位、環境濕度、緩慢升降的管道壓力。
* **優缺點**：過渡平滑，最符合物理連續性；但不適用於突變值或開關訊號。

### 2. 前向填充 / 後向填充 (Forward / Backward Fill)
* **公式原理**：
  * **FFill (Last Observation Carried Forward)**：用缺失前最近一次的有效值直接複製填充。
  * **BFill (Next Observation Carried Backward)**：用缺失後最近一次的有效值複製填充。
* **適用場景**：**狀態值與控制設定值**。例如：閥門狀態（0/1）、馬達運轉/停止、設定壓力目標值、班次代碼。
* **優缺點**：簡單直接，保證數據階梯性；但會對連續變化量造成「時間滯後」效能。

### 3. 移動平均補值 (Rolling Mean Imputation)
* **公式原理**：取缺失點前後鄰近共 $N$ 個小時的有效值平均數作為填補值。
* **適用場景**：**具備隨機噪聲的波動數據**。例如：煙道風速、即時用電負荷。
* **優缺點**：能平滑短期異常噪聲；但會消除極值（峰值/谷值）。

### 4. 歷史同期平均 (Historical / Seasonal Imputation)
* **公式原理**：若缺失區間較長（如整整 2 天），則參考前幾週「同星期幾、同小時」的平均值進行填補。
* **適用場景**：**具備強烈日/週規律的生產與能源數據**。例如：每日排程流量、廠房用電量、冷卻水塔日照時數。
* **優缺點**：能捕捉日夜與工作日/週末的週期規律；但無法反映當天的即時突發狀況。

---

## 四、 補值腳本實作範例 (Python)

以下是建議的 Python 實作藍圖，該腳本會：
1. 讀取 SQLite 檔案中點位資料。
2. 對齊時間網格，篩選出缺失點。
3. 採用「**線性插補 + 邊界前後填充**」的黃金組合進行補值。
4. 將乾淨的資料寫入新的資料表 `C_SCADA_DataArchive_Imputed`。

```python
import sqlite3
import pandas as pd
import numpy as np

def impute_scada_data(db_path: str):
    conn = sqlite3.connect(db_path)
    
    # 1. 讀取原始資料
    query = "SELECT Id, point_id, PointName, Value, Timestamp FROM C_SCADA_DataArchive"
    df = pd.read_sql_query(query, conn)
    
    # 將時間與數值轉換為標準格式
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce') # 強制將 NaN 字串或空值轉為 float 的 NaN
    
    # 2. 定義 6 月份標準每小時時間網格
    all_hours = pd.date_range(start="2026-06-01 00:00:00", end="2026-06-30 23:00:00", freq="h")
    
    imputed_records = []
    
    # 3. 按點位 (point_id) 分組處理
    for (point_id, point_name), group in df.groupby(['point_id', 'PointName']):
        # 去除重複時間點（以防萬一）
        group = group.drop_duplicates(subset=['Timestamp'])
        
        # 將 Timestamp 設為 Index，並重新對齊網格
        group = group.set_index('Timestamp')
        aligned = group.reindex(all_hours)
        
        # 填充欄位資訊
        aligned['point_id'] = point_id
        aligned['PointName'] = point_name
        
        # 統計缺失前狀態
        missing_count = aligned['Value'].isna().sum()
        
        # 4. 執行補值演算法
        # - 先進行線性插補 (Linear Interpolation)
        # - 若缺失在頭尾無法插補，使用 ffill 與 bfill 補齊
        aligned['Value'] = aligned['Value'].interpolate(method='linear').ffill().bfill()
        
        # 重設 Index 恢復 Timestamp 欄位
        aligned = aligned.reset_index().rename(columns={'index': 'Timestamp'})
        imputed_records.append(aligned)
        
        print(f"點位 {point_name} (ID: {point_id})：已補值 {missing_count}/720 個小時點。")
    
    # 合併所有點位資料
    final_df = pd.concat(imputed_records, ignore_index=True)
    
    # 5. 寫入新資料表 (保留原始 raw 資料)
    final_df.to_sql("C_SCADA_DataArchive_Imputed", conn, if_exists="replace", index=False)
    conn.close()
    print("✨ 補值完成！資料已寫入新資料表 C_SCADA_DataArchive_Imputed。")

if __name__ == "__main__":
    # 使用時傳入您的 SQLite 檔案路徑
    impute_scada_data("data/sif_sqlite.db")
```

---

## 五、 下一步建議與討論

在正式開發補值程式前，建議先確認：
1. **補值範圍**：是否針對目前 SQLite 中有出現的所有 `point_id`（共 16 個）皆採用此補值流程？
2. **極端狀況處理**：若某點位有連續超過 48 小時（2天以上）的長期缺失，單純使用線性插補可能會失真。是否需要設定「**最大連續補值時間上限**」（例如：連續缺失大於 12 小時則不補值，標記為異常）？
