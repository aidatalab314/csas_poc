# CSAS PoC — 人流安全感知系統

**Crowd Safety Awareness System — Proof of Concept**

以 AI 視覺模型驗證車站、捷運站等公共空間的即時安全感知能力。本系統採獨立架設、不介接既有 CCTV、不修改車站網路，可快速部署與拆除。

---

## 驗證場域

| 場域 | 位置 | 偵測項目 | 執行腳本 |
|------|------|---------|---------|
| Space A | 車站大廳 / 開放式通道 | 人流密度、滯留物、異常快速移動 | `src/run_space_a.py` |
| Space B | 樓梯 / 狹窄通道 | 群眾恐慌性移動、通道擁擠 | `src/run_space_b.py` |
| Space C | 月台模擬區域 | 跨越警戒線、限制區域入侵、大型物件入侵 | `src/run_space_c.py` |

---

## 實驗室網路架構

```
MacBook (140.124.42.77)
    │
    │  靜態路由：192.168.6.0/24 → 192.168.0.87
    ▼
Ubuntu Server
    ├── 192.168.0.87  (內網，Mac 可直連)
    └── 192.168.6.87  (Camera 子網路，iptables NAT 轉發)
                │
                ├── Camera A (KMRT-1)  192.168.6.90  ✅
                └── Camera B (KMRT-2)  192.168.6.91  ✅
```

### Mac 開發環境網路設定（一次性）

**Mac 端 — 新增靜態路由：**

```bash
# 暫時生效（重開機後消失）
sudo route add -net 192.168.6.0/24 192.168.0.87

# 永久生效
sudo networksetup -setadditionalroutes "Ethernet" 192.168.6.0 255.255.255.0 192.168.0.87
```

> 介面名稱（`Ethernet`）可用 `networksetup -listallnetworkservices` 確認。

**Ubuntu 端 — 開啟 IP 轉發與 NAT（一次性）：**

```bash
# IP 轉發（已確認 = 1）
sudo sysctl -w net.ipv4.ip_forward=1

# NAT Masquerade（Camera 子網路回程）
sudo iptables -t nat -A POSTROUTING -o eno1 -j MASQUERADE

# 允許 FORWARD（Docker 環境下需明確允許）
sudo iptables -I FORWARD -d 192.168.6.0/24 -j ACCEPT
sudo iptables -I FORWARD -s 192.168.6.0/24 -j ACCEPT
```

> Ubuntu 重開機後 iptables 規則會消失，需重新執行或設定 `iptables-persistent`。

### RTSP 位址

| Camera | ID | RTSP URL |
|--------|----|----------|
| KMRT-1 | `camera_a` | `rtsp://root:root@192.168.6.90/cam1/h264` |
| KMRT-2 | `camera_b` | `rtsp://root:root@192.168.6.91/cam1/h264` |

---

## 系統需求

- Python 3.9+
- OpenCV、Ultralytics YOLO（見 `requirements.txt`）

### 建立虛擬環境

```bash
cd /path/to/csas_poc

# 建立 venv（名稱自訂）
python3 -m venv csas_env

# 啟動（Mac / Linux）
source csas_env/bin/activate

# 安裝套件
pip install -r requirements.txt
```

> 啟動環境後，以下所有指令直接用 `python` 執行即可。

---

## 快速開始

### 步驟 1 — 準備模型

將 YOLO 模型放至 `models/person_detection/`：

```
models/
└── person_detection/
    └── yolo11n.pt    # 或 yolo11s.pt / yolov8n.pt 等
```

> 首次執行若無模型，ultralytics 會自動下載 `yolo11n.pt`。

`configs/cameras.yaml` 中的 `detector.model` 路徑可自行修改。

### 步驟 2 — 確認影像來源

```bash
# 確認兩台 Camera 可連線
python3 -c "import cv2; cap = cv2.VideoCapture('rtsp://root:root@192.168.6.90/cam1/h264'); print('camera_a:', cap.isOpened()); cap.release()"
python3 -c "import cv2; cap = cv2.VideoCapture('rtsp://root:root@192.168.6.91/cam1/h264'); print('camera_b:', cap.isOpened()); cap.release()"
```

**影像來源優先順序：** `--source` 參數 → `cameras.yaml` source（RTSP）→ fallback 本地影片

### 步驟 3 — ROI 設定

#### 自動 ROI 檢查（推薦）

每個 run script 啟動時會自動檢查攝影機是否有 ROI 設定，若無則引導互動設定：

```
[ROI | Space A] camera_b: 尚無 ROI 設定
[ROI | Space A]   此場域建議類型：zone
[ROI | Space A] 是否現在設定 ROI？[Y/n]: Y
[ROI | Space A] 開啟 zone 繪製視窗…
──────────────────────────────────────
[ROI] 視窗已關閉，請回到此終端機繼續操作
──────────────────────────────────────
```

> **視窗關閉後**請立即回到終端機，程式會繼續等待輸入。

#### 手動 ROI 設定（`scripts/setup_roi.py`）

```bash
# Space A / B — 繪製偵測區（zone）
python scripts/setup_roi.py \
  --camera camera_a \
  --source "rtsp://root:root@192.168.6.90/cam1/h264" \
  --type zone

python scripts/setup_roi.py \
  --camera camera_b \
  --source "rtsp://root:root@192.168.6.91/cam1/h264" \
  --type zone

# Space C — 繪製限制區域（zone）
python scripts/setup_roi.py \
  --camera camera_c \
  --source "rtsp://root:root@192.168.6.90/cam1/h264" \
  --type zone

# Space C — 繪製警戒線（line）
python scripts/setup_roi.py \
  --camera camera_c \
  --source "rtsp://root:root@192.168.6.90/cam1/h264" \
  --type line

# 查看所有 ROI 設定
python scripts/setup_roi.py --list

# 清除並重新繪製
python scripts/setup_roi.py \
  --camera camera_a \
  --source "rtsp://root:root@192.168.6.90/cam1/h264" \
  --type zone --reset
```

#### ROI 操作說明

| 按鍵 | 動作 |
|------|------|
| 左鍵點擊 | 加入頂點 |
| 右鍵點擊 | 刪除最後一個頂點 |
| `C` | 確認當前 ROI（zone ≥ 3 點，line = 2 點） |
| `R` | 重置當前未完成 ROI |
| `ESC` / `Q` | 儲存並結束 |

#### ROI 資料設計

| Camera | 使用場域 | 建議 ROI 類型 |
|--------|---------|-------------|
| `camera_a` | Space A | zone |
| `camera_b` | Space A（多路）/ Space B | zone |
| `camera_c` | Space C | zone + line |

- 同一 camera 的 zone 與 line 設定互不影響
- 重複設定同類型時，新設定會**取代**舊設定（不累加），避免 ROI 衝突
- 無 ROI 設定時系統以全幀為偵測範圍（無圍籬模式）

### 步驟 4 — 執行場域驗證

#### Space A — 車站大廳（支援多攝影機）

```bash
# 單台（預設 camera_a）
python src/run_space_a.py

# 單台 + 指定影像來源
python src/run_space_a.py --cameras camera_a --source 0
python src/run_space_a.py --cameras camera_a --source data/demo_videos/hall.mp4
python src/run_space_a.py --cameras camera_a \
  --source "rtsp://root:root@192.168.6.90/cam1/h264"

# 雙攝影機同時執行（split-screen 並排單視窗顯示）
python src/run_space_a.py --cameras camera_a,camera_b
```

多攝影機模式以 **split-screen** 顯示，單一視窗左右並排，各 camera 畫面獨立推論：

```
┌──────────────────┬──────────────────┐
│  camera_a        │  camera_b        │
│  [偵測畫面]      │  [偵測畫面]      │
│  People:2 FPS:18 │  People:1 FPS:17 │
└──────────────────┴──────────────────┘
         CSAS PoC — Space A
```

> 每台攝影機各自擁有 Detector / Tracker / ROI / EventManager，互不干擾。跨攝影機 ReID 保留至第二階段。

#### Space B — 樓梯 / 狹窄通道

```bash
python src/run_space_b.py
python src/run_space_b.py --source data/demo_videos/camera_b.mp4
```

#### Space C — 月台模擬

```bash
python src/run_space_c.py
python src/run_space_c.py --source data/demo_videos/camera_c.mp4
```

---

## 專案結構

```
csas_poc/
├── configs/
│   ├── cameras.yaml          # 攝影機來源、偵測器、場域門檻值、效能設定
│   ├── roi_records.json      # ROI 設定（由 setup_roi.py / ensure_roi 自動產生）
│   └── event_rules.yaml      # 事件規則說明（參考用）
│
├── data/
│   ├── demo_videos/          # 放置本地測試影片
│   ├── snapshots/            # 事件觸發時自動截圖
│   └── logs/                 # 事件 JSON log
│
├── models/
│   ├── person_detection/     # 人員偵測模型（yolo11n.pt 等）
│   ├── abandoned_object/     # 滯留物偵測模型（可替換）
│   └── fire_smoke/           # 火煙偵測（第二階段）
│
├── src/
│   ├── run_space_a.py        # Space A 執行入口（支援多攝影機 split-screen）
│   ├── run_space_b.py        # Space B 執行入口
│   ├── run_space_c.py        # Space C 執行入口
│   ├── main.py               # 通用執行入口
│   ├── detector.py           # YOLO 偵測器（可替換模型）
│   ├── preprocessor.py       # 影像前處理（Gamma 校正 + CLAHE）
│   ├── tracker.py            # 質心追蹤器（dwell time / 速度計算）
│   ├── roi_engine.py         # ROI 規則引擎、互動設定工具、ensure_roi
│   ├── event_manager.py      # 事件輸出（Console / Log / Snapshot）
│   ├── visualizer.py         # 繪製工具
│   └── utils.py              # 設定讀取、log
│
├── scripts/
│   └── setup_roi.py          # 互動式 ROI 繪製工具（手動使用）
│
├── tests/
│   ├── test_tracker.py
│   └── test_roi_engine.py
│
└── requirements.txt
```

---

## 介面顯示說明

### Space A — 車站大廳

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
| `Zone 0:2  Zone 1:1` | **各 ROI 偵測區的即時人數**（無 ROI 時顯示 `People:N`） |
| `FPS:18.3` | 該攝影機執行緒的實際畫面率 |
| `skip:2` | 隔幀推論模式（每 2 幀推論一次）；為 1 時不顯示 |

---

### Space B — 樓梯 / 狹窄通道

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
│  Zone 0:4                     ← 白字狀態列         │
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
| `CROWD RUSH Zone 0` | 同時有 N 人超速（N ≥ `rush_person_count`），事件綁定實際 zone 名稱 |
| `CONGESTION Zone 0` | 通道人數超過 `congestion_alert_count` |

---

### Space C — 月台模擬

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
│  Persons: 2  Objects: 1       ← 白字狀態列         │
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

### 共用說明

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
| `large_object_intrusion` | Space C | high |

---

## 各場域設定說明

### Space A — 車站大廳（`configs/cameras.yaml`）

```yaml
# 全域預設值（各攝影機可個別覆蓋）
space_a:
  crowd_alert_count: 5           # 區域內人數超過此值觸發
  abandoned_alert_seconds: 15.0  # 物件無人陪伴超過此秒數觸發
  abandoned_proximity_px: 120    # 物件與最近人距離超過此值視為無陪伴
  speed_alert_px_per_frame: 20   # 人員移動速度門檻（px/frame）
  speed_alert_person_count: 2    # 幾人同時快速移動才觸發
```

### Space B — 樓梯 / 狹窄通道

```yaml
rush_speed_px_per_frame: 25    # 恐慌移動速度門檻
rush_person_count: 3           # 幾人同時快速移動觸發 crowd_rush
congestion_alert_count: 8      # 區域內人數超過此值觸發擁擠警報
```

> **聲音事件偵測（YOHO）**：第一版為佔位模式，`_audio_placeholder()` 預留整合位置。

### Space C — 月台模擬

```yaml
large_object_classes: [28]     # COCO class 28 = suitcase；可擴充 [24, 26, 28]
```

ROI 設定為主要控制手段，建議至少設定一條警戒線（line）與一個限制區域（zone）。

---

## 偵測器替換

```yaml
detector:
  model: "models/person_detection/yolo11n.pt"   # 替換此路徑
  conf: 0.4
  device: "mps"   # Apple M1/M2/M3 → "mps" | CPU → "cpu" | Jetson → "0"
  imgsz: 640      # 推論解析度：640（平衡）/ 480（更快）/ 1280（遠距細節）
```

---

## 影像前處理

推論前可選擇性套用前處理技術，改善車站混合光源、暗區、逆光等場景的偵測率。

```yaml
detector:
  preprocess:
    gamma: 1.0        # Gamma 校正：1.0 = 關閉；< 1 提亮暗部（建議 0.5~0.8）
    clahe: false      # CLAHE 自適應對比增強：混合光源 / 逆光場景建議開啟
    clahe_clip: 3.0   # clipLimit（2.0~4.0，越高對比越強）
    clahe_grid: [8, 8]
```

| 技術 | 原理 | 適用場景 |
|------|------|---------|
| **Gamma 校正** | LUT 查表法，`gamma < 1` 提亮暗部 | 夜間、角落暗區 |
| **CLAHE** | 自適應直方圖均衡化（LAB L 通道） | 強逆光、陰影邊界、室內外混合光 |
| **imgsz** | YOLO 推論解析度 | 高解析度 RTSP、遠距小目標 |

| 場景 | 建議設定 |
|------|---------|
| 光源均勻（日間大廳） | `gamma: 1.0, clahe: false`（預設） |
| 暗區 / 夜間 | `gamma: 0.6, clahe: true` |
| 強逆光 / 出入口 | `gamma: 1.0, clahe: true, clahe_clip: 4.0` |
| 高解析度 RTSP + 遠距目標 | `imgsz: 1280` |

---

## 效能優化（Mac / 開發環境）

開發機為 **Apple M1 Mac mini**，已套用以下優化：

### 1. MPS 加速

```yaml
detector:
  device: "mps"   # Apple Silicon Metal GPU，推論速度比 CPU 快 3~5×
```

### 2. 單次 YOLO 推論

Space A 原先 person + object 分開兩個 Detector，現改為一次推論再按 class_id 拆分，雙路攝影機下 inference 次數從 4 → 2。

### 3. Frame Skip（隔幀推論）

```yaml
detector:
  inference_skip_frames: 2   # 每 2 幀推論一次，顯示仍連續
```

畫面狀態列即時顯示 FPS 與 skip 模式：
```
People:2  FPS:18.3  skip:2
```

### 4. RTSP Buffer 優化

RTSPReader 開啟時自動設定 `CAP_PROP_BUFFERSIZE = 1`，消除 OpenCV 預設 buffer 堆積舊幀的延遲。

### 調校建議

| 情境 | `device` | `inference_skip_frames` | `imgsz` |
|------|---------|------------------------|---------|
| M1 MPS 雙路流暢 | `mps` | `1` | `640` |
| M1 MPS 仍有壓力 | `mps` | `2` | `480` |
| CPU 單路 | `cpu` | `2` | `640` |
| Jetson TensorRT | `"0"` | `1` | `640` |

---

## Jetson Orin 部署

### 步驟 0 — 確認型號與 JetPack 版本

```bash
cat /proc/device-tree/model
cat /etc/nv_tegra_release
nvcc --version
tegrastats
```

| 型號 | GPU 記憶體 | 適合場景 |
|------|-----------|---------|
| AGX Orin 64GB | 64 GB 共用 | 多路 Camera + 高解析度 |
| AGX Orin 32GB | 32 GB 共用 | 雙路 Camera，本專案主力目標 |
| Orin NX 16GB | 16 GB 共用 | 單路 Camera，輕量部署 |
| Orin NX 8GB | 8 GB 共用 | 單路 Camera，資源受限 |
| Orin Nano 8GB / 4GB | 8/4 GB 共用 | 測試驗證用 |

### 步驟 1 — Python 環境建立

```bash
python3 -m venv csas_env
source csas_env/bin/activate

# PyTorch ARM64 wheel（JetPack 6.x / CUDA 12.6）
pip install torch torchvision \
  --index-url https://pypi.jetson-ai-lab.dev/jp6/cu126/

pip install -r requirements.txt
```

### 步驟 2 — TensorRT 加速

```bash
# 在 Jetson 上匯出（FP16）
yolo export \
  model=models/person_detection/yolo11n.pt \
  format=engine device=0 imgsz=640 half=True

mv yolo11n.engine models/person_detection/
```

更新 `cameras.yaml`：

```yaml
detector:
  model: "models/person_detection/yolo11n.engine"
  device: "0"
  imgsz: 640
```

### 步驟 3 — 效能設定

```bash
sudo nvpmodel -m 0      # 最高功耗模式（MAXN）
sudo jetson_clocks      # 鎖定最高時脈
tegrastats --interval 1000   # 確認 GR3D_FREQ > 0%
```

| 型號 | `imgsz` | `inference_skip_frames` |
|------|---------|------------------------|
| AGX Orin 32/64GB | 1280 | `1` |
| Orin NX 16GB | 640 | `1` |
| Orin NX 8GB | 640 | `2` |
| Orin Nano | 480 | `2` |

### Jetson 網路拓樸

```
IP Camera (192.168.6.90 / .91)
        │
        └── 直連 Jetson (192.168.6.x)
```

Jetson 直連 Camera 子網路，不需要 Mac 的靜態路由或 iptables 設定。

---

## 第一版 PoC 完成條件

- [x] RTSP Camera 可運作（兩路已驗證）
- [x] AI 模型可即時推論（YOLO11n）
- [x] ROI 規則可觸發事件
- [x] 事件 Snapshot 保存
- [x] 事件 JSON Log 輸出
- [x] 系統可獨立展示，不需修改車站既有設施
- [x] Mac 直連實驗室 IP Camera（靜態路由 + iptables NAT）
- [x] Space A 多攝影機 split-screen 同時監控
- [x] 啟動時自動 ROI 檢查與引導設定（ensure_roi）
- [x] Apple M1 MPS 加速 + frame skip 效能優化

## 第二階段（暫不優先）

- [ ] 聲音 AI 分析（YOHO 整合）
- [ ] 多攝影機 Re-ID
- [ ] 火光煙霧偵測
- [ ] Jetson Orin TensorRT 加速部署
- [ ] DeepStream Pipeline 整合
