import cv2
from pathlib import Path
from src.utils import log


def _is_file_source(src) -> bool:
    """判斷來源是否為本地檔案路徑（非 RTSP / 非整數 webcam index）。"""
    if isinstance(src, int):
        return False
    s = str(src)
    return not s.startswith("rtsp://") and not s.startswith("rtmp://") and not s.isdigit()


def _resolve_source(src):
    """將字串 webcam index 轉為 int，其餘原樣回傳。"""
    if isinstance(src, int):
        return src
    return int(src) if str(src).isdigit() else src


class RTSPReader:
    """
    影像來源讀取器。
    優先嘗試 source，失敗時自動切換 fallback（本地影片或 USB cam）。
    本地檔案來源在嘗試開啟前先確認是否存在，並給出明確提示。
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

        # 本地檔案：先確認存在
        if _is_file_source(src):
            p = Path(str(src))
            if not p.exists():
                log("WARN", f"{label} 檔案不存在，跳過: {src}")
                return False

        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(src)
        if self.cap.isOpened():
            self.active_source = src
            # RTSP：將解碼 buffer 縮到 1 幀，避免舊幀堆積造成顯示延遲
            if isinstance(src, str) and (src.startswith("rtsp://") or
                                          src.startswith("rtmp://")):
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
