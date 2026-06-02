# CSAS PoC 專案上下文文件（供 Claude Code 使用）

# 1. 專案名稱

CSAS PoC — 人流安全感知系統（Crowd Safety Awareness System）

---

# 2. 專案目標

本專案目標為建立一套「最快可執行」的 AI 人流安全感知 PoC（Proof of Concept）系統，用於驗證 AI 模型於車站、捷運站或大型公共空間中的即時安全感知能力。

本 PoC 需在：

- 不影響既有 CCTV 系統
- 不修改既有網路架構
- 不影響旅客動線
- 不干擾既有監控設備

之前提下，快速完成部署與驗證。

本系統應能獨立運作、可快速拆裝、可攜帶部署，並具備後續擴充至正式系統之能力。

---

# 3. PoC 核心原則

系統需遵守以下限制：

- 不介接既有車站 CCTV
- 不修改既有車站網路
- 不影響旅客動線
- 不影響既有監控設備
- 所有設備由專案團隊自行架設與管理
- 採用可快速部署與拆除之設備架設方式
- 第一版以「完整可執行」優先，而非架構完整性
- 第一版以 AI 推論驗證為核心，不建立完整平台系統

---

# 4. 最快可執行 MVP 範圍

第一版 MVP 聚焦於：

```text
RTSP Camera / Local Video
            ↓
Frame Decode
            ↓
AI Model Inference
            ↓
ROI Rule Detection
            ↓
Event Trigger
            ↓
Console / Local Log Output
```

第一版不需要：

- Dashboard
- API Server
- Docker
- Web UI
- 使用者系統
- 權限管理
- 資料庫系統
- 雲端架構

第一版重點：

「讓 AI 模型可以真正跑起來並完成事件偵測」

---

# 5. PoC 驗證場景

## 空間 A：車站大廳 / 開放式通道

### 使用 AI 模型
- 區域人流偵測
- 滯留物偵測
- 異常移動偵測

### 驗證內容
- 放置背包、行李箱
- 模擬多人快速移動
- 模擬多人於區域產生異常移動

### 架設方式
- Camera A 架設於開放式通道側邊
- 採斜向俯視角度
- 高度約 2.5~3 公尺
- 使用工業型三腳架固定

---

## 空間 B：樓梯 / 狹窄通道

### 使用 AI 模型
- 群眾恐慌性移動偵測
- 聲音事件偵測
- 跨域追蹤

### 驗證內容
- 模擬群體快速移動
- 模擬求救聲、呼喊聲
- 測試跨攝影機人員追蹤

### 架設方式
- Camera B 架設於樓梯口或狹窄通道入口上方
- 高度約 2.5 公尺
- 使用工業型三腳架固定

---

## 空間 C：月台模擬區域

### 使用 AI 模型
- 月台跨線 / 限制區域入侵偵測

### 驗證內容
- 模擬跨越警戒線
- 模擬人員進入限制區域
- 模擬大型物件進入限制區域

### 架設方式
- 利用地面標線建立虛擬電子圍籬
- 使用攝影機俯視方式進行驗證

---

# 6. 第二階段驗證項目（暫不優先）

以下項目視為後續擴充：

- 火光煙霧偵測（以影片辨識驗證為主）
- 大型物件落軌偵測（以影片辨識驗證為主）
- 聲音 AI 分析優化
- 多攝影機 Re-ID 強化
- DeepStream 加速
- TensorRT 優化

目前不應阻塞第一版 PoC。

---

# 7. 硬體假設

PoC 預計使用：

```text
2 × 車站規格 IP Camera
1 × AI 邊緣運算裝置
1 × 集中運算主機
1 × 網路交換器
1~2 × 麥克風
2 × 工業型三腳架
```

---

# 8. 系統架構

## 8.1 感知層（Sensing Layer）

負責蒐集影像與聲音資料。

元件：

- Camera A
- Camera B
- Microphone（可選）
- RTSP / ONVIF
- Audio Stream

用途：

- Camera A：大廳 / 通道區域
- Camera B：樓梯 / 月台模擬區域

---

## 8.2 邊緣 AI 層（Edge AI Layer）

負責即時 AI 推論。

主要功能：

- RTSP 串流讀取
- Frame Decode
- AI 模型推論
- ROI 規則判斷
- 單攝影機追蹤
- 事件觸發
- 本地事件紀錄

第一版建議技術：

```text
Python
OpenCV
Ultralytics YOLO
YOHO
NumPy
```

後續可加入：

```text
TensorRT
DeepStream
ONNX Runtime
ByteTrack
```

但第一版先避免過度優化。

---

# 9. 建議 Repository Structure

```text
csas-poc/
├── README.md
│
├── configs/
│   ├── cameras.yaml
│   ├── roi_config.yaml
│   └── event_rules.yaml
│
├── data/
│   ├── snapshots/
│   ├── logs/
│   └── demo_videos/
│
├── models/
│   ├── person_detection/
│   ├── abandoned_object/
│   └── fire_smoke/
│
├── src/
│   ├── main.py
│   ├── rtsp_reader.py
│   ├── detector.py
│   ├── tracker.py
│   ├── roi_engine.py
│   ├── event_manager.py
│   ├── visualizer.py
│   └── utils.py
│
├── tests/
│
└── scripts/
```

---

# 10. Event Output Format

所有事件需統一格式：

```json
{
  "event_type": "line_crossing",
  "camera_id": "camera_b",
  "roi_id": "platform_zone",
  "timestamp": "2026-01-01T12:00:00+08:00",
  "severity": "high",
  "confidence": 0.92
}
```

第一版可直接：

- print console
- save txt log
- save snapshot

不需要建立 API。

---

# 11. Claude Code 開發規則

Claude Code 必須遵守：

1. 優先完成「能跑」的版本
2. 不過度工程化
3. 不建立完整平台系統
4. 不建立前後端架構
5. 不建立微服務
6. 不建立 Docker 架構
7. 優先本地單機執行
8. Config 優先於 DB
9. 無 RTSP 時可使用USB cam或是本地影片
10. AI 模型需可替換
11. ROI 規則需模組化
12. 所有流程需有 logging
13. README 必須清楚說明如何啟動
14. 每個功能需可獨立測試

---

# 12. 第一階段開發 Milestone

## Milestone 1 — RTSP Reader

建立：

- RTSP Reader

RTSP Addresses (測試)
IP Camera Lab Jinwei: rtsp://admin:123456@192.168.3.123/stream0
IP Camera Lab KMRT-1: rtsp://root:root@192.168.6.90/cam1/h264
IP Camera Lab KMRT-2: rtsp://root:root@192.168.6.91/cam1/h264

Python RTSP Access code
```python
import cv2

rtsp_url = "rtsp://root:root@192.168.6.90/cam1/h264"

cap = cv2.VideoCapture(rtsp_url)

if cap.isOpened():
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        cv2.imshow("RTSP Stream", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
cap.release()
cv2.destroyAllWindows()
```


- Local Video Fallback
- Frame Display

完成條件：

可穩定讀取影像。

---

## Milestone 2 — Person Detection

建立：

- YOLOvXXn / YOLOvXXs 推論
- YOHO

完成條件：

可穩定偵測人員 Bounding Box 以及聲音辨識

---

## Milestone 3 — ROI Rule Engine

建立：

- 區域入侵
- 跨線
- 停留時間判定

完成條件：

可觸發事件。

---

## Milestone 4 — Snapshot & Logging

建立：

- Snapshot Save
- Event TXT Log
- Console Event Output

完成條件：

可保存事件結果。

---

## Milestone 5 — 雙攝影機 Demo

完成：

- 同時處理兩路影像
- 多 ROI 驗證
- 多事件觸發

完成條件：

可展示完整 PoC。

---

# 13. 本地執行目標

第一版需可直接：

```bash
python src/main.py
```

或：

```bash
python src/main.py --config configs/cameras.yaml
```

即可運作。

---

# 14. Demo 策略

第一版 Demo 建議：

1. 使用本地影片
2. 完成完整事件流程
3. 再替換成 RTSP Camera

流程：

```text
影片 / Camera
    ↓
AI 推論
    ↓
ROI Rule
    ↓
Event Trigger
    ↓
Console / Snapshot / Log
```

---

# 15. 第一版 PoC 完成定義（Definition of Done）

以下條件成立即視為 PoC 成功：

- 至少一個影像來源可運作
- 至少一個 AI 模型可即時推論
- 至少一個 ROI 規則可觸發事件
- 可保存事件 Snapshot
- 可輸出 Event Log
- 系統可獨立展示
- 不需修改車站既有基礎設施

---

# 16. 最重要架構決策

第一版不要直接導入：

- Docker
- API
- Dashboard
- 微服務
- DeepStream
- Multi-Agent
- Database

請先完成：

```text
OpenCV + YOLO + YOHO + Python
```

目標是：

「最快建立可運作的人流安全 AI 驗證系統」
