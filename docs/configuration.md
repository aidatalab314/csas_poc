# 設定說明

## cameras.yaml 各場域參數

### Space A — 車站大廳

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
# 全域預設值（各攝影機可個別覆蓋）
space_b:
  rush_speed_px_per_frame: 25    # 恐慌移動速度門檻（px/frame）
  rush_person_count: 3           # 幾人同時快速移動觸發 crowd_rush
  congestion_alert_count: 8      # 區域內人數超過此值觸發擁擠警報
```

> **聲音事件偵測（YOHO）**：第一版為佔位模式，`_audio_placeholder()` 預留整合位置。

### Space C — 月台模擬

```yaml
# 全域預設值（各攝影機可個別覆蓋）
space_c:
  large_object_classes: [28]     # COCO class 28 = suitcase；可擴充 [24, 26, 28]
```

ROI 設定為主要控制手段，建議至少設定一條警戒線（line）與一個限制區域（zone）。

---

## 偵測器替換

`configs/cameras.yaml` 的 `detector` 區塊控制模型與推論設定：

```yaml
detector:
  model: "models/person_detection/yolo11n.pt"   # 替換此路徑即可換模型
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
    gamma: 0.5        # Gamma 校正：1.0 = 關閉；< 1 提亮暗部（建議 0.5~0.8）
    clahe: true       # CLAHE 自適應對比增強：混合光源 / 逆光場景建議開啟
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

## 效能優化

### MPS 加速（Apple Silicon）

```yaml
detector:
  device: "mps"   # Apple Silicon Metal GPU，推論速度比 CPU 快 3~5×
```

### Frame Skip（隔幀推論）

```yaml
detector:
  inference_skip_frames: 3   # 每 3 幀推論一次，顯示仍連續
```

狀態列即時顯示 FPS 與 skip 模式：
```
Zone 0:2  FPS:18.3  skip:3
```

### RTSP Buffer

RTSPReader 開啟時自動設定 `CAP_PROP_BUFFERSIZE = 1`，消除 OpenCV 預設 buffer 堆積舊幀的延遲。

### 調校建議

| 情境 | `device` | `inference_skip_frames` | `imgsz` |
|------|---------|------------------------|---------|
| M1 MPS 雙路流暢 | `mps` | `1` | `640` |
| M1 MPS 仍有壓力 | `mps` | `3` | `480` |
| CPU 單路 | `cpu` | `2` | `640` |
| Jetson TensorRT | `"0"` | `1` | `640` |

---

## 顯示縮放

Space B / C 的預覽視窗縮放比例由全域 `display.scale` 統一控制：

```yaml
display:
  scale: 0.7   # Space B/C 縮放係數；Space A 使用 PANEL_H split-screen，不受此影響
```

若需要特定攝影機使用不同縮放，可在該 camera entry 加 `display_scale: 0.8` 覆蓋。

---

## Mac ↔ Jetson 快速切換

只需修改 `configs/cameras.yaml` 的 `detector.device`：

| 環境 | `device` | 說明 |
|------|---------|------|
| Mac M1/M2/M3 | `"mps"` | Apple Silicon Metal GPU |
| Mac Intel / Linux CPU | `"cpu"` | 純 CPU 推論 |
| Jetson Orin | `"0"` | CUDA GPU（確認後 GR3D_FREQ > 0%） |

```bash
# Mac → Jetson
sed -i 's/device: "mps"/device: "0"/' configs/cameras.yaml

# Jetson → Mac
sed -i 's/device: "0"/device: "mps"/' configs/cameras.yaml
```

Jetson 完整部署步驟見 [docs/jetson.md](jetson.md)。
