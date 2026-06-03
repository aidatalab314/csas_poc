import cv2
from pathlib import Path
from src.utils import log


def _is_file_source(src) -> bool:
    if isinstance(src, int):
        return False
    s = str(src)
    return not s.startswith("rtsp://") and not s.startswith("rtmp://") and not s.isdigit()


def _is_rtsp_source(src) -> bool:
    if isinstance(src, int):
        return False
    s = str(src)
    return s.startswith("rtsp://") or s.startswith("rtmp://")


def _resolve_source(src):
    if isinstance(src, int):
        return src
    return int(src) if str(src).isdigit() else src


def _build_gst_rtsp_pipeline(rtsp_url: str) -> str:
    return (
        f"rtspsrc location={rtsp_url} latency=0 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=1 max-buffers=1 sync=false"
    )


class RTSPReader:
    """
    影像來源讀取器。
    RTSP 來源優先使用 GStreamer nvv4l2decoder 硬體解碼（Jetson），
    失敗時自動 fallback 到 FFmpeg 軟體解碼（Mac / 開發環境）。
    本地檔案 / webcam 直接使用 cv2.VideoCapture 預設 backend。
    """

    def __init__(self, source, fallback=None):
        self.source = source
        self.fallback = fallback
        self.cap = None
        self.active_source = None

    def open(self) -> bool:
        if self._try_open(self.source, label="主要來源"):
            return True

        if self.fallback is not None:
            log("WARN", f"主要來源失敗，切換備援: {self.fallback}")
            if self._try_open(self.fallback, label="備援"):
                return True

        log("ERROR", "無法開啟任何影像來源。")
        log("ERROR", "建議：")
        log("ERROR", "  1. 使用 USB webcam：  --source 0")
        log("ERROR", "  2. 指定本地影片：     --source /path/to/video.mp4")
        log("ERROR", "  3. 指定 RTSP 串流：   --source rtsp://...")
        return False

    def _try_open(self, src, label: str) -> bool:
        src = _resolve_source(src)

        if _is_file_source(src):
            p = Path(str(src))
            if not p.exists():
                log("WARN", f"{label} 檔案不存在，跳過: {src}")
                return False

        if self.cap:
            self.cap.release()

        # RTSP：優先嘗試 GStreamer 硬體解碼（Jetson nvv4l2decoder）
        # Mac 沒有 nvv4l2decoder，VideoCapture 會回傳 isOpened()=False，自動走 fallback
        if _is_rtsp_source(src):
            gst_pipe = _build_gst_rtsp_pipeline(str(src))
            cap = cv2.VideoCapture(gst_pipe, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self.cap = cap
                self.active_source = src
                log("INFO", f"已開啟 {label}（GStreamer 硬體解碼）: {src}")
                return True
            cap.release()
            log("WARN", f"{label}: GStreamer 不可用，改用 FFmpeg: {src}")

        # 一般來源 或 GStreamer 失敗時 fallback（FFmpeg）
        self.cap = cv2.VideoCapture(src)
        if self.cap.isOpened():
            self.active_source = src
            if _is_rtsp_source(src):
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            log("INFO", f"已開啟 {label}: {src}")
            return True

        self.cap.release()
        self.cap = None
        log("WARN", f"{label} 無法開啟: {src}")
        return False

    def read(self):
        if self.cap is None:
            return False, None
        return self.cap.read()

    def is_opened(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def get_fps(self) -> float:
        return self.cap.get(cv2.CAP_PROP_FPS) or 25.0

    def get_size(self) -> tuple[int, int]:
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return w, h

    def release(self):
        if self.cap:
            self.cap.release()
            self.cap = None
