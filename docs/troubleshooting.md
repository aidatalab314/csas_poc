# 常見問題排除

---

## GStreamer：RTSP 串流無法開啟 / 畫面全黑（H.265 pipeline 設定錯誤）

**症狀：** GStreamer pipeline `isOpened()=False`，或開啟後畫面全黑

**原因：** 實驗室 AXIS 攝影機的 RTSP URL 路徑雖含 `h264`，實際串流編碼為 **H.265（HEVC）**。
若 pipeline 使用 `rtph264depay`，GStreamer 無法解碼，`VideoCapture` 開啟失敗或靜音。

**正確 pipeline（已內建至 `rtsp_reader.py`）：**
```python
"rtspsrc location={rtsp_url} latency=0 ! "
"rtph265depay ! h265parse ! nvv4l2decoder ! "
"nvvidconv ! video/x-raw,format=BGRx ! "
"videoconvert ! video/x-raw,format=BGR ! "
"appsink drop=true max-buffers=1 sync=false"
```

> **注意：** `appsink drop=true` 必須小寫（GStreamer property 格式），`drop=True` 會被忽略導致 buffer 累積延遲。

---

## GStreamer：`get_size()` 回傳 (0, 0)

**症狀：** CUDA warmup 使用 (0,0) 解析度，主循環開始時 JIT 重新編譯，首幀延遲數秒

**原因：** GStreamer live source 在第一幀到達前，caps 尚未協商完成，`CAP_PROP_FRAME_WIDTH / HEIGHT` 回傳 0。

**解法（已內建至 `rtsp_reader.py get_size()`）：** 偵測到 0×0 時預讀第一幀（`cap.read()`），從 `frame.shape` 取得真實解析度，並快取此幀供主循環使用，不丟棄。

---

## CUDA warmup 應使用真實 frame 解析度

**症狀：** warmup 完成後主循環首幀仍有明顯延遲（JIT 重新觸發）

**原因：** 若 warmup 時使用固定的 `(640, 640)` 假幀，而實際 RTSP 串流解析度不同（如 1920×1080），CUDA JIT 仍會在真實幀到達時重新編譯。

**解法（已內建至 `run_space_a.py`）：**
```python
w, h = reader.get_size()          # 取得真實攝影機解析度
detector.detect(np.zeros((h, w, 3), dtype=np.uint8))  # warmup 使用真實尺寸
```

---

## Jetson：cv2.imshow 黑畫面 / Qt crash

**症狀：** `qt.qpa.xcb: could not connect to display` 或視窗全黑

**原因：** pip 版 `opencv-python` 自帶 Qt5，其 xcb plugin 無法連到 Jetson X display。

**解法：**
1. 移除 pip 版（包含 user-local）：`pip3 uninstall opencv-python numpy -y`
2. 重建 venv（見 [docs/jetson.md 步驟 1](jetson.md#步驟-1--python-環境建立)），使用系統 OpenCV
3. 設定 SSH 顯示環境（見 [docs/jetson.md 顯示環境設定](jetson.md#顯示環境設定ssh-連線)）

---

## Jetson：`numpy.core.multiarray failed to import` / `_ARRAY_API not found`

**原因：** pip 安裝的 numpy 2.x 與 JetPack 系統 OpenCV / torch 不相容（均以 numpy 1.x 編譯）。

**解法：**
```bash
pip uninstall numpy -y
pip install "numpy>=1.23.0,<2"
```

---

## Jetson：GTK backend 無法初始化

**原因：** SSH session 缺少 X 認證資訊。

**解法：**
```bash
# SSH session 中設定
export DISPLAY=:0
export XAUTHORITY=/run/user/1000/gdm/Xauthority

# Jetson 實體螢幕 terminal 執行
xhost +local:
```
