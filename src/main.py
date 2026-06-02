"""
CSAS PoC — 人流安全感知系統
Entry point.

用法：
    python src/main.py                              # 依 cameras.yaml 順序執行所有攝影機
    python src/main.py --config configs/cameras.yaml
    python src/main.py --camera camera_a            # 只執行指定攝影機
    python src/main.py --camera camera_a --source data/demo_videos/test.mp4
    python src/main.py --camera camera_a --source 0  # USB webcam
"""

import argparse
import sys
import cv2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rtsp_reader import RTSPReader
from src.detector import Detector
from src.tracker import CentroidTracker
from src.roi_engine import ROIEngine
from src.event_manager import EventManager
from src.visualizer import draw_detections, draw_tracked, draw_alert_bar
from src.utils import load_yaml, log

ROI_RECORDS = "configs/roi_records.json"


def run_camera(cam_cfg: dict, det_cfg: dict, out_cfg: dict):
    camera_id = cam_cfg["id"]
    source = cam_cfg.get("source", 0)
    fallback = cam_cfg.get("fallback")
    dwell_threshold = cam_cfg.get("dwell_alert_seconds", 10.0)
    display_scale = cam_cfg.get("display_scale", 0.7)

    log("INFO", f"啟動 {camera_id} ({cam_cfg.get('name', '')})")

    reader = RTSPReader(source, fallback=fallback)
    if not reader.open():
        return

    detector = Detector(
        model_path=det_cfg["model"],
        conf=det_cfg.get("conf", 0.4),
        device=det_cfg.get("device", "cpu"),
        target_classes=det_cfg.get("target_classes"),
    )

    tracker = CentroidTracker(
        max_disappeared=det_cfg.get("tracker_max_disappeared", 30),
        max_match_px=det_cfg.get("tracker_max_match_px", 150),
    )
    roi = ROIEngine(camera_id, ROI_RECORDS)
    events = EventManager(
        camera_id,
        snapshot_dir=out_cfg.get("snapshot_dir", "data/snapshots"),
        log_dir=out_cfg.get("log_dir", "data/logs"),
        save_snapshots=out_cfg.get("save_snapshots", True),
    )

    log("INFO", f"{camera_id}: zones={len(roi.zones)}, lines={len(roi.lines)}")

    active_alerts: list[str] = []

    while reader.is_opened():
        ret, frame = reader.read()
        if not ret:
            break

        # ── 繪製 ROI ────────────────────────────────────────────────────────
        roi.draw(frame)

        # ── AI 推論 ─────────────────────────────────────────────────────────
        detections = detector.detect(frame)
        dets_in_roi = [d for d in detections if roi.is_in_any_zone(d["cx"], d["cy"])]

        # ── 追蹤 ─────────────────────────────────────────────────────────────
        tracked = tracker.update(dets_in_roi)

        # ── 繪製偵測結果 ──────────────────────────────────────────────────────
        draw_detections(frame, dets_in_roi)
        draw_tracked(frame, tracked, dwell_threshold=dwell_threshold)

        # ── ROI 規則判斷 ──────────────────────────────────────────────────────
        active_alerts.clear()

        for obj_id, obj in tracked.items():
            cx, cy = obj["cx"], obj["cy"]
            conf = obj["det"].get("conf", 0.5)

            # 滯留時間
            if obj["dwell_seconds"] >= dwell_threshold:
                for zone_label in roi.get_zone_labels(cx, cy):
                    triggered = events.trigger(
                        event_type="dwell_alert",
                        roi_id=zone_label,
                        severity="medium",
                        confidence=conf,
                        frame=frame,
                    )
                    if triggered:
                        active_alerts.append(f"DWELL ID:{obj_id} @ {zone_label}")

            # 跨線偵測
            for line_label in roi.check_line_crossing(obj_id, cx, cy):
                triggered = events.trigger(
                    event_type="line_crossing",
                    roi_id=line_label,
                    severity="high",
                    confidence=conf,
                    frame=frame,
                )
                if triggered:
                    active_alerts.append(f"LINE CROSS ID:{obj_id} -> {line_label}")

        if active_alerts:
            draw_alert_bar(frame, active_alerts[0])

        preview = cv2.resize(frame, None, fx=display_scale, fy=display_scale)
        cv2.imshow(f"CSAS PoC - {camera_id}", preview)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break

    reader.release()
    cv2.destroyAllWindows()
    log("INFO", f"{camera_id} 已停止")


def main():
    parser = argparse.ArgumentParser(description="CSAS PoC — 人流安全感知系統")
    parser.add_argument("--config", default="configs/cameras.yaml")
    parser.add_argument("--camera", default=None, help="指定 camera id")
    parser.add_argument("--source", default=None,
                        help="覆蓋影像來源 (RTSP URL / 影片路徑 / webcam index)")
    args = parser.parse_args()

    cfg = load_yaml(args.config)
    det_cfg = cfg.get("detector", {})
    out_cfg = cfg.get("output", {})
    cameras = cfg.get("cameras", [])

    if args.camera:
        cameras = [c for c in cameras if c["id"] == args.camera]
        if not cameras:
            log("ERROR", f"找不到 camera id: {args.camera}")
            sys.exit(1)

    if args.source:
        src = int(args.source) if args.source.isdigit() else args.source
        for cam in cameras:
            cam["source"] = src
            cam.pop("fallback", None)

    for cam_cfg in cameras:
        run_camera(cam_cfg, det_cfg, out_cfg)


if __name__ == "__main__":
    main()
