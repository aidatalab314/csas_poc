# 介面顯示說明

## ROI 設定

### 自動 ROI 檢查（啟動時）

每個 run script 啟動時會自動檢查攝影機是否有 ROI 設定，若無則引導互動設定：

```
[ROI | Space A] camera_a: 尚無 ROI 設定
[ROI | Space A]   此場域建議類型：zone
[ROI | Space A] 是否現在設定 ROI？[Y/n]: Y
[ROI | Space A] 開啟 zone 繪製視窗…
──────────────────────────────────────
[ROI] 視窗已關閉，請回到此終端機繼續操作
──────────────────────────────────────
```

> **視窗關閉後**請立即回到終端機，程式會繼續等待輸入。

### 手動設定（scripts/setup_roi.py）

```bash
# Space A / B — 繪製偵測區（zone）
python scripts/setup_roi.py --camera camera_a --source "rtsp://root:root@192.168.6.90/cam1/h264" --type zone
python scripts/setup_roi.py --camera camera_b --source "rtsp://root:root@192.168.6.91/cam1/h264" --type zone

# Space C — 限制區域（zone）
python scripts/setup_roi.py --camera camera_c --source "rtsp://root:root@192.168.6.90/cam1/h264" --type zone

# Space C — 警戒線（line）
python scripts/setup_roi.py --camera camera_c --source "rtsp://root:root@192.168.6.90/cam1/h264" --type line

# 查看所有設定
python scripts/setup_roi.py --list

# 清除並重繪
python scripts/setup_roi.py --camera camera_a --source "rtsp://..." --type zone --reset
```

### 操作快捷鍵

| 按鍵 | 動作 |
|------|------|
| 左鍵點擊 | 加入頂點 |
| 右鍵點擊 | 刪除最後一個頂點 |
| `C` | 確認當前 ROI（zone ≥ 3 點，line = 2 點） |
| `R` | 重置當前未完成 ROI |
| `ESC` / `Q` | 儲存並結束 |

### ROI 資料設計

| Camera | 使用場域 | 建議 ROI 類型 |
|--------|---------|-------------|
| `camera_a` | Space A | zone |
| `camera_b` | Space A（多路）/ Space B | zone |
| `camera_c` | Space C | zone + line |

- 重複設定同類型時，新設定會**取代**舊設定（不累加），避免 ROI 衝突
- 無 ROI 設定時系統以全幀為偵測範圍（無圍籬模式）

---

## Space A — 車站大廳

```
┌─────────────────────────┬─────────────────────────┐
│  camera_a               │  camera_b               │  ← 黑底青字，panel 標題
├─────────────────────────┴─────────────────────────┤
│                                                   │
│  ╔══════════════════╗                             │
│  ║  (半透明填色)     ║  Zone 0  ← ROI 偵測區      │
│  ╚══════════════════╝                             │
│                                                   │
│  ┌──────────┐                                     │
│  │ person   │  ← 綠色框                           │
│  │  0.87    │  ← 類別 + 信心分數                  │
│  └────●─────┘  ← 綠色圓點（bbox 中心）             │
│    ID:0 2.3s   ← 追蹤 ID + 已追蹤秒數             │
│                                                   │
│  ┌──────────┐                                     │
│  │ suitcase │  ← 橘色框（偵測中）                  │
│  │  12s     │  ← 類別 + 已滯留秒數                │
│  └──────────┘  ※ 超過滯留門檻且無人陪伴 → 深紅色框  │
│                                                   │
│    ──→          ← 紅色箭頭（快速移動者位移向量）    │
│                                                   │
├───────────────────────────────────────────────────┤
│  Zone 0:2  Zone 1:1  FPS:18.3  skip:2            │  ← 白字狀態列
└───────────────────────────────────────────────────┘

觸發事件 → 頂端紅色警報列（三擇一）：
  CROWD Zone 0: 5 persons        ← 該 zone 人數超過門檻
  ABANDONED: suitcase ID:2       ← 滯留物無人陪伴超時
  FAST MOVE: 3 persons           ← 多人快速移動
```

| 元素 | 說明 |
|------|------|
| `camera_a` / `camera_b` | split-screen 各 panel 的攝影機 ID |
| 半透明多邊形 `Zone N` | 已設定的 ROI 偵測區，顏色輪替 |
| 綠色框 `person 0.87` | YOLO 偵測到的人員（信心分數 0~1） |
| 橘黃色圓點 `ID:N X.Xs` | 追蹤 ID + 已被追蹤的累計秒數 |
| 橘色框 `suitcase 12s` | 背包 / 行李箱偵測中，未超過滯留門檻 |
| 深紅色框 `suitcase 18s` | 超過 `abandoned_alert_seconds` 且附近無人 |
| 紅色箭頭 | 速度超過 `speed_alert_px_per_frame` 的人員位移向量 |
| `Zone 0:2  Zone 1:1` | 各 ROI 偵測區的即時人數（無 ROI 時顯示 `People:N`） |
| `FPS:18.3` | 該攝影機執行緒的實際畫面率 |
| `skip:2` | 隔幀推論模式；為 1 時不顯示 |

---

## Space B — 樓梯 / 狹窄通道

```
┌───────────────────────────────────────────────────┐
│  ╔══════════════════╗                             │
│  ║  Zone 0          ║  ← ROI 通道區               │
│  ╚══════════════════╝                             │
│                                                   │
│  ┌──────────┐                                     │
│  │ person   │  ← 綠色框                           │
│  └────●─────┘                                     │
│    ID:1 5.2s                                      │
│    ※ 正常速度者不顯示速度數值                       │
│                                                   │
│  ┌──────────┐                                     │
│  │ person   │                                     │
│  └────●─────┘  ◎  ← 紅色雙圓（超速者專屬標記）    │
│    ID:3 1.0s                                      │
│    spd:32px   ← 紅色，只有超過門檻者才顯示         │
│                                                   │
├───────────────────────────────────────────────────┤
│  Zone 0:4                     FPS:25.3            │
└───────────────────────────────────────────────────┘

觸發事件 → 頂端深紅色警報列：
  CROWD RUSH Zone 0: 3 persons   ← 多人同時超速移動
  CONGESTION Zone 0: 8 persons   ← 通道人數超過門檻
```

| 元素 | 說明 |
|------|------|
| 紅色雙圓 `◎` | 速度超過 `rush_speed_px_per_frame` 的人員 |
| `spd:32px` | 超速者本幀移動的像素距離（僅超速者顯示） |
| `Zone 0:N` | ROI 通道區內的即時人數（無 ROI 時顯示 `People:N`） |
| `CROWD RUSH` | 同時有 N 人超速（N ≥ `rush_person_count`），事件綁定實際 zone 名稱 |
| `CONGESTION` | 通道人數超過 `congestion_alert_count` |

---

## Space C — 月台模擬

```
┌───────────────────────────────────────────────────┐
│  ╔══════════════════╗                             │
│  ║  Zone 0 (限制區) ║  ← 半透明多邊形              │
│  ╚══════════════════╝                             │
│                                                   │
│  ════════════════ Line 0  ← 警戒線（實心帶標籤）   │
│                                                   │
│  ┌──────────┐                                     │
│  │ person   │  ← 亮綠色框 (0,220,0)               │
│  │  0.88    │                                     │
│  └────●─────┘                                     │
│    ID:0 3.1s                                      │
│                                                   │
│  ┌──────────┐  ← 橘色框，大型物件                  │
│  │ suitcase │                                     │
│  └────●─────┘                                     │
│                                                   │
│  ╔══════════╗                                     │
│  ║ person   ║  ← 紅色粗框（入侵警告）              │
│  ║INTRUSION ║  ← 類型 + zone 名稱（紅字）          │
│  ║  Zone 0  ║                                     │
│  ╚══════════╝                                     │
│                                                   │
├───────────────────────────────────────────────────┤
│  Persons:2  Objects:1         FPS:28.4            │
└───────────────────────────────────────────────────┘

觸發事件 → 頂端深藍色警報列（四種）：
  LINE CROSS: person ID:1 → Line 0        ← 人員跨線
  INTRUSION: person ID:2 in Zone 0        ← 人員入侵限制區
  OBJ CROSS: suitcase ID:3 → Line 0      ← 物件跨線
  OBJ INTRUSION: suitcase ID:3 in Zone 0 ← 物件入侵限制區
```

| 元素 | 說明 |
|------|------|
| 半透明多邊形 `Zone N` | 限制區域，人員 / 物件進入即觸發 |
| 實心線 `Line N` | 警戒線，跨越即觸發（方向感知） |
| 亮綠色框 | YOLO 偵測到的人員 |
| 橘色框 | YOLO 偵測到的大型物件（行李箱等） |
| 紅色粗框 `CROSS` | 人員本幀跨越警戒線 |
| 深藍框 `INTRUSION` | 人員進入限制區域 |
| 藍橘框 `OBJ CROSS` / `OBJ IN` | 大型物件跨線 / 入侵限制區 |
| `Persons:N  Objects:N` | 全幀偵測到的人員數 + 大型物件數 |

---

## 共用說明

| 元素 | 說明 |
|------|------|
| 警報列持續時間 | 冷卻 3 秒才重複觸發同一事件，避免重複閃爍 |
| `ID:N` | 追蹤器指派的唯一 ID，同一人在畫面內 ID 不變 |
| `X.Xs` | 該目標已被追蹤的累計秒數（自進入畫面起計） |
| `Q` / `ESC` | 關閉所有視窗並停止系統 |

---

## 事件輸出格式

所有事件以 JSON 格式輸出至 Console 並寫入 `data/logs/`，同時在 `data/snapshots/` 儲存截圖：

```json
{
  "event_type": "crowd_density_alert",
  "camera_id": "camera_a",
  "roi_id": "Zone 0",
  "timestamp": "2026-06-01T15:35:08.613947+08:00",
  "severity": "medium",
  "confidence": 1.0
}
```

> `roi_id` 使用 ROI 設定時的實際標籤名稱（`Zone 0`、`Line 0` 等），而非硬編碼字串。

### 各場域事件類型

| event_type | 場域 | severity |
|------------|------|----------|
| `crowd_density_alert` | Space A | medium |
| `abandoned_object` | Space A | high |
| `abnormal_movement` | Space A | medium |
| `crowd_rush` | Space B | high |
| `congestion_alert` | Space B | medium |
| `line_crossing` | Space C | high |
| `zone_intrusion` | Space C | high |
| `large_object_line_crossing` | Space C | high |
| `large_object_intrusion` | Space C | high |
