# Jetson Orin 部署

## 步驟 0 — 確認型號與 JetPack 版本

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

---

## 步驟 1 — Python 環境建立

> **重要：** Jetson 必須使用 JetPack 內建的系統 OpenCV（GTK backend），**不可** 用 `pip install opencv-python`。
> pip 版 opencv-python 自帶 Qt5 library，其 xcb plugin 無法連到 Jetson 的 X display，會導致 `cv2.imshow` 黑畫面或 crash。

```bash
# 建立 venv 並帶入系統 OpenCV（--system-site-packages 關鍵）
python3 -m venv csas_env --system-site-packages
source csas_env/bin/activate

# 安裝套件，不裝 opencv-python（改用系統版）
# numpy 必須 < 2：JetPack 系統 OpenCV 與 Jetson torch 均以 numpy 1.x 編譯
pip install "numpy>=1.23.0,<2" ultralytics pyyaml loguru

# 確認 OpenCV 來自系統路徑（應為 /usr/lib/python3.10/dist-packages/cv2/...）
python3 -c "import cv2; print(cv2.__version__, cv2.__file__)"
# 確認 CUDA 可用
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

---

## 步驟 2 — TensorRT 加速

```bash
# 在 Jetson 上匯出（FP16）
yolo export \
  model=models/person_detection/yolo11n.pt \
  format=engine device=0 imgsz=640 half=True

mv yolo11n.engine models/person_detection/
```

更新 `configs/cameras.yaml`：

```yaml
detector:
  model: "models/person_detection/yolo11n.engine"
  device: "0"
  imgsz: 640
```

---

## 步驟 3 — 效能設定

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

---

## 顯示環境設定（SSH 連線）

```bash
# 加入 ~/.bashrc，之後每次 SSH 自動生效
echo 'export DISPLAY=:0' >> ~/.bashrc
echo 'export XAUTHORITY=/run/user/1000/gdm/Xauthority' >> ~/.bashrc

# 在 Jetson 實體螢幕的 terminal 執行一次（允許 SSH session 存取 X）
xhost +local:
```

---

## 驗證

```bash
# GPU 推論確認
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# 顯示確認
python3 -c "
import cv2, numpy as np
img = np.zeros((480,640,3), dtype=np.uint8)
cv2.rectangle(img, (100,100), (540,380), (0,255,0), -1)
cv2.imshow('test', img)
cv2.waitKey(3000)
cv2.destroyAllWindows()
"

# 即時 GPU 負載監控（推論中 GR3D_FREQ 應 > 0%）
tegrastats --interval 1000
```

---

## 網路拓樸

```
IP Camera (192.168.6.90 / .91)
        │
        └── 直連 Jetson (192.168.6.x)
```

Jetson 直連 Camera 子網路，不需要 Mac 的靜態路由或 iptables 設定。

Mac 開發環境的網路設定見 [docs/network.md](network.md)。
