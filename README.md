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

## 系統需求

- Python 3.9+
- OpenCV、Ultralytics YOLO（見 `requirements.txt`）

### 建立虛擬環境（Mac / Linux）

```bash
cd /path/to/csas_poc
python3 -m venv csas_env
source csas_env/bin/activate
pip install -r requirements.txt
```

> Jetson 環境建立方式不同，見 [docs/jetson.md](docs/jetson.md)。

---

## 快速開始

### 步驟 1 — 準備模型

將 YOLO 模型放至 `models/person_detection/`：

```
models/person_detection/
└── yolo11n.pt    # 或 yolo11s.pt / yolov8n.pt 等
```

> 首次執行若無模型，ultralytics 會自動下載 `yolo11n.pt`。

### 步驟 2 — 確認影像來源

**影像來源優先順序：** `--source` 參數 → `cameras.yaml` source（RTSP）→ fallback 本地影片

```bash
# 確認 Camera 可連線（實驗室環境）
python3 -c "import cv2; cap = cv2.VideoCapture('rtsp://root:root@192.168.6.90/cam1/h264'); print('camera_a:', cap.isOpened()); cap.release()"
```

> 實驗室網路設定（靜態路由、Ubuntu iptables）見 [docs/network.md](docs/network.md)。

### 步驟 3 — ROI 設定

每個 run script 啟動時會自動檢查 ROI，若無設定則引導互動設定。

也可手動執行：

```bash
python scripts/setup_roi.py --camera camera_a --source "rtsp://..." --type zone
python scripts/setup_roi.py --list   # 查看所有設定
```

> ROI 操作說明與顯示元素說明見 [docs/display.md](docs/display.md)。

### 步驟 4 — 執行場域驗證

#### 執行模式

| 模式 | 說明 | 適用情境 |
|------|------|---------|
| `--mode dev`（預設）| 顯示即時畫面、偵測框、警報列 | 開發、展示、ROI 調校 |
| `--mode op` | 無畫面，定期 log 狀態 + 即時輸出警報 | Jetson 正式部署 |

#### 執行模式說明：正常模式 vs 測試影片模式

| 情況 | ROI 行為 | 錄影輸出 |
|------|---------|---------|
| **無 `--source`**（正常模式）| 讀取 `roi_records.json` 已存設定，首次才引導繪製 | 無 |
| **有 `--source`**（測試影片模式）| 每次強制重新互動繪製，**不寫入** `roi_records.json` | 自動儲存至 `data/test_recordings/` |

#### Space A — 車站大廳（支援多攝影機）

```bash
# 正常模式（RTSP，讀已存 ROI）
python src/run_space_a.py --cameras camera_a

# 測試影片模式（每次重畫 ROI，自動錄影）
python src/run_space_a.py --cameras camera_a --source data/demo_videos/panic_video.mp4

# 雙攝影機 split-screen（正常模式）
python src/run_space_a.py --cameras camera_a,camera_b

# 作業模式（無畫面）
python src/run_space_a.py --cameras camera_a,camera_b --mode op
```

雙攝影機 split-screen 顯示：
```
┌──────────────────┬──────────────────┐
│  camera_a        │  camera_b        │
│  [偵測畫面]      │  [偵測畫面]      │
│  Zone 0:2  FPS:30│  Zone 0:1  FPS:29│
└──────────────────┴──────────────────┘
         CSAS PoC — Space A
```

#### Space B — 樓梯 / 狹窄通道

```bash
# 正常模式
python src/run_space_b.py

# 測試影片模式
python src/run_space_b.py --source data/demo_videos/camera_b.mp4

python src/run_space_b.py --mode op
```

#### Space C — 月台模擬

```bash
# 正常模式
python src/run_space_c.py

# 測試影片模式
python src/run_space_c.py --source data/demo_videos/camera_c.mp4

python src/run_space_c.py --mode op
```

---

## 專案結構

```
csas_poc/
├── configs/
│   ├── cameras.yaml          # 攝影機來源、偵測器、場域門檻值、效能設定
│   ├── roi_records.json      # ROI 設定（由 setup_roi.py / ensure_roi 自動產生）
│   └── event_rules.yaml      # 事件規則說明（參考用）
├── data/
│   ├── demo_videos/          # 本地測試影片
│   ├── test_recordings/      # 測試影片模式的偵測結果錄影（自動產生）
│   ├── snapshots/            # 事件觸發截圖
│   └── logs/                 # 事件 JSON log
├── docs/
│   ├── network.md            # 實驗室網路架構 + Mac/Ubuntu 設定
│   ├── configuration.md      # 場域參數、偵測器、前處理、效能優化
│   ├── display.md            # 介面顯示說明 + ROI 操作 + 事件格式
│   ├── jetson.md             # Jetson Orin 完整部署步驟
│   └── troubleshooting.md    # 常見問題排除
├── models/
│   └── person_detection/     # YOLO 模型（yolo11n.pt / .engine）
├── src/
│   ├── run_space_a.py        # Space A 執行入口（多攝影機 split-screen）
│   ├── run_space_b.py        # Space B 執行入口
│   ├── run_space_c.py        # Space C 執行入口
│   ├── main.py               # 通用執行入口
│   ├── detector.py           # YOLO 偵測器
│   ├── preprocessor.py       # 影像前處理（Gamma + CLAHE）
│   ├── tracker.py            # 質心追蹤器
│   ├── roi_engine.py         # ROI 規則引擎 + ensure_roi
│   ├── event_manager.py      # 事件輸出（Console / Log / Snapshot）
│   ├── rtsp_reader.py        # 影像來源讀取（RTSP / 本地 / webcam）
│   ├── visualizer.py         # 繪製工具
│   └── utils.py              # 設定讀取、log
├── scripts/
│   └── setup_roi.py          # 互動式 ROI 繪製工具
└── tests/
    ├── test_tracker.py
    └── test_roi_engine.py
```

---

## 詳細文件

| 文件 | 說明 |
|------|------|
| [docs/network.md](docs/network.md) | 實驗室網路架構、Mac 靜態路由、Ubuntu iptables、RTSP 位址 |
| [docs/configuration.md](docs/configuration.md) | cameras.yaml 參數、偵測器替換、前處理、效能優化、Mac↔Jetson 切換 |
| [docs/display.md](docs/display.md) | 介面顯示說明、ROI 操作、事件輸出格式 |
| [docs/jetson.md](docs/jetson.md) | Jetson Orin 完整部署（venv、TensorRT、顯示設定） |
| [docs/troubleshooting.md](docs/troubleshooting.md) | GStreamer、Jetson OpenCV、numpy、GTK backend 問題排除 |

---

## 第一版 PoC 完成條件

- [x] RTSP Camera 可運作（兩路已驗證，H.265）
- [x] AI 模型可即時推論（YOLO11n）
- [x] ROI 規則可觸發事件
- [x] 事件 Snapshot 保存
- [x] 事件 JSON Log 輸出
- [x] 系統可獨立展示，不需修改車站既有設施
- [x] Mac 直連實驗室 IP Camera（靜態路由 + iptables NAT）
- [x] Space A 多攝影機 split-screen 同時監控
- [x] 啟動時自動 ROI 檢查與引導設定（ensure_roi）
- [x] Apple M1 MPS 加速 + frame skip 效能優化
- [x] Jetson Orin TensorRT FP16 加速（yolo11n.engine）
- [x] Jetson GStreamer nvv4l2decoder H.265 硬體解碼
- [x] dev / op 雙模式：開發者顯示畫面 / 作業模式無畫面純 log
- [x] 測試影片模式：`--source` 自動觸發，ROI 每次重畫不存檔，偵測結果自動錄影至 `data/test_recordings/`

## 第二階段（暫不優先）

- [ ] 聲音 AI 分析（YOHO 整合）
- [ ] 多攝影機 Re-ID
- [ ] 火光煙霧偵測
- [ ] DeepStream Pipeline 整合
