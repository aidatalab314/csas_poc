import json
import cv2
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_TAIPEI = timezone(timedelta(hours=8))
_COOLDOWN_SEC = 3.0  # 同一事件類型最短觸發間隔，避免重複刷屏


class EventManager:
    """
    事件輸出管理器。
    - Console JSON 輸出
    - TXT 事件 log
    - Snapshot 截圖（可選）
    """

    def __init__(self, camera_id: str,
                 snapshot_dir: str = "data/snapshots",
                 log_dir: str = "data/logs",
                 save_snapshots: bool = True):
        self.camera_id = camera_id
        self.snapshot_dir = Path(snapshot_dir)
        self.log_dir = Path(log_dir)
        self.save_snapshots = save_snapshots
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"events_{camera_id}_{ts}.txt"

        # cooldown: (event_type, roi_id) -> last triggered timestamp
        self._last_triggered: dict[tuple, float] = {}

    def trigger(self, event_type: str, roi_id: str,
                severity: str, confidence: float,
                frame=None) -> bool:
        """
        觸發事件。回傳 True 表示事件成功觸發（未在冷卻中）。
        """
        import time
        key = (event_type, roi_id)
        now = time.time()
        if now - self._last_triggered.get(key, 0) < _COOLDOWN_SEC:
            return False
        self._last_triggered[key] = now

        ts = datetime.now(tz=TZ_TAIPEI).isoformat()
        event = {
            "event_type": event_type,
            "camera_id": self.camera_id,
            "roi_id": roi_id,
            "timestamp": ts,
            "severity": severity,
            "confidence": round(confidence, 4),
        }

        line = json.dumps(event, ensure_ascii=False)
        print(f"[EVENT] {line}")

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        if self.save_snapshots and frame is not None:
            snap_name = (f"{event_type}_{self.camera_id}_"
                         f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg")
            cv2.imwrite(str(self.snapshot_dir / snap_name), frame)

        return True
