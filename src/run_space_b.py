"""
Space B — 樓梯 / 狹窄通道
==========================
偵測項目：
  1. 群眾恐慌性移動   → N 人同時快速移動觸發 crowd_rush
  2. 通道擁擠         → 人數超過門檻觸發 congestion_alert
  3. 聲音事件偵測     → [MVP 佔位] YOHO 音訊模型預留位置

使用 Camera B（樓梯 / 狹窄通道）。

用法：
    python src/run_space_b.py
    python src/run_space_b.py --source data/demo_videos/camera_b.mp4
    python src/run_space_b.py --source rtsp://root:root@192.168.6.91/cam1/h264
    python src/run_space_b.py --source 0
"""

import argparse
import sys
import math
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rtsp_reader import RTSPReader
from src.detector import Detector
from src.preprocessor import Preprocessor
from src.tracker import CentroidTracker
from src.roi_engine import ROIEngine, ensure_roi
from src.event_manager import EventManager
from src.visualizer import draw_detections, draw_tracked, draw_alert_bar
from src.utils import load_yaml, log

CLASS_PERSON = [0]

CAMERA_ID = "camera_b"
ROI_RECORDS = "configs/roi_records.json"
CONFIG_PATH = "configs/cameras.yaml"


def _draw_speed_overlay(frame: np.ndarray,
                        speeds: dict[int, float],
                        tracked: dict,
                        rush_threshold: float):
    """超速者標記紅色圓圈與速度數值；正常速度者不顯示數值（減少視覺雜訊）。"""
    for obj_id, speed in speeds.items():
        if obj_id not in tracked:
            continue
        cx, cy = tracked[obj_id]["cx"], tracked[obj_id]["cy"]
        if speed > rush_threshold:
            cv2.circle(frame, (cx, cy), 14, (0, 0, 255), 2)
            cv2.putText(frame, f"spd:{speed:.0f}px", (cx + 10, cy + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)


def _audio_placeholder():
    """YOHO 音訊偵測佔位：MVP 版本僅輸出提示。"""
    # TODO: 整合 YOHO 音訊事件偵測模型
    # yoho = YOHODetector(model_path="models/audio/yoho.pt")
    # events = yoho.detect(audio_stream)
    pass


def run(source=None):
    cfg = load_yaml(CONFIG_PATH)
    cam_cfg = next(c for c in cfg["cameras"] if c["id"] == CAMERA_ID)
    det_cfg = cfg["detector"]
    out_cfg = cfg["output"]

    src = source if source is not None else cam_cfg.get("source")
    fallback = None if source is not None else cam_cfg.get("fallback")
    display_scale = cam_cfg.get("display_scale", 0.7)

    rush_speed = cam_cfg.get("rush_speed_px_per_frame", 25)
    rush_count = cam_cfg.get("rush_person_count", 3)
    congestion_count = cam_cfg.get("congestion_alert_count", 8)

    log("INFO", f"[Space B] 啟動  source={src}")
    log("INFO", "[Space B] 聲音事件偵測：MVP 版本為佔位模式（YOHO 尚未整合）")

    # 啟動前自動 ROI 檢查
    ensure_roi(CAMERA_ID,
               source=src,
               fallback=fallback,
               records_path=ROI_RECORDS,
               scene_name="Space B",
               expected_types=["zone"])

    reader = RTSPReader(src, fallback=fallback)
    if not reader.open():
        return

    pre = Preprocessor.from_config(det_cfg.get("preprocess", {}))
    if not pre.is_noop:
        log("INFO", f"[Space B] 前處理已啟用: {det_cfg.get('preprocess')}")

    detector = Detector(
        det_cfg["model"], conf=det_cfg.get("conf", 0.4),
        device=det_cfg.get("device", "cpu"),
        target_classes=CLASS_PERSON,
        imgsz=det_cfg.get("imgsz", 640),
        preprocessor=pre,
    )

    tracker = CentroidTracker(max_disappeared=25)
    roi = ROIEngine(CAMERA_ID, ROI_RECORDS)
    events = EventManager(
        CAMERA_ID,
        snapshot_dir=out_cfg.get("snapshot_dir", "data/snapshots"),
        log_dir=out_cfg.get("log_dir", "data/logs"),
        save_snapshots=out_cfg.get("save_snapshots", True),
    )

    log("INFO", f"[Space B] zones={len(roi.zones)}, lines={len(roi.lines)}")

    prev_pos: dict[int, tuple[int, int]] = {}
    active_alerts: list[str] = []

    while reader.is_opened():
        ret, frame = reader.read()
        if not ret:
            break

        roi.draw(frame)

        # ── 偵測與追蹤 ────────────────────────────────────────────────────────
        dets = detector.detect(frame)
        dets_in_roi = [d for d in dets if roi.is_in_any_zone(d["cx"], d["cy"])]
        tracked = tracker.update(dets_in_roi)

        draw_detections(frame, dets_in_roi)
        draw_tracked(frame, tracked)

        # 狀態列：各 zone 人數（Space B 通常單一 zone）
        if roi.zones:
            zone_str = "  ".join(
                f"{z['label']}:{sum(1 for obj in tracked.values() if z['label'] in roi.get_zone_labels(obj['cx'], obj['cy']))}"
                for z in roi.zones
            )
        else:
            zone_str = f"People:{len(tracked)}"
        cv2.putText(frame, zone_str, (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        active_alerts.clear()

        # ── 速度計算 ──────────────────────────────────────────────────────────
        current_speeds: dict[int, float] = {}
        for obj_id, obj in tracked.items():
            cx, cy = obj["cx"], obj["cy"]
            prev = prev_pos.get(obj_id)
            if prev is not None:
                current_speeds[obj_id] = math.hypot(cx - prev[0], cy - prev[1])
            prev_pos[obj_id] = (cx, cy)

        for gone_id in list(prev_pos.keys()):
            if gone_id not in tracked:
                del prev_pos[gone_id]

        _draw_speed_overlay(frame, current_speeds, tracked, rush_speed)

        # 取當前所有 zone 標籤（無 ROI 時用預設名稱）
        roi_labels = [z["label"] for z in roi.zones] or ["zone_b"]

        # ── 規則 1：群眾恐慌性移動 ────────────────────────────────────────────
        fast_persons = [oid for oid, spd in current_speeds.items()
                        if spd > rush_speed]
        if len(fast_persons) >= rush_count:
            events.trigger(
                event_type="crowd_rush",
                roi_id=roi_labels[0],
                severity="high",
                confidence=min(1.0, len(fast_persons) / rush_count),
                frame=frame,
            )
            active_alerts.append(f"CROWD RUSH {roi_labels[0]}: {len(fast_persons)} persons")

        # ── 規則 2：通道擁擠 ──────────────────────────────────────────────────
        if len(tracked) >= congestion_count:
            events.trigger(
                event_type="congestion_alert",
                roi_id=roi_labels[0],
                severity="medium",
                confidence=1.0,
                frame=frame,
            )
            active_alerts.append(f"CONGESTION {roi_labels[0]}: {len(tracked)} persons")

        # ── 規則 3：聲音事件（佔位）──────────────────────────────────────────
        _audio_placeholder()

        if active_alerts:
            draw_alert_bar(frame, active_alerts[0], color=(180, 0, 0))

        preview = cv2.resize(frame, None, fx=display_scale, fy=display_scale)
        cv2.imshow("CSAS PoC — Space B (樓梯/通道)", preview)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    reader.release()
    cv2.destroyAllWindows()
    log("INFO", "[Space B] 已停止")


def main():
    parser = argparse.ArgumentParser(description="Space B — 樓梯 / 狹窄通道")
    parser.add_argument("--source", default=None,
                        help="影像來源：影片路徑 / RTSP URL / webcam index")
    args = parser.parse_args()
    src = int(args.source) if args.source and args.source.isdigit() else args.source
    run(source=src)


if __name__ == "__main__":
    main()
