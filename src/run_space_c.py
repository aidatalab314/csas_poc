"""
Space C — 月台模擬區域
======================
偵測項目：
  1. 跨越警戒線       → line_crossing（人員 / 大型物件）
  2. 限制區域入侵     → zone_intrusion（人員進入禁止區）
  3. 大型物件入侵     → large_object_intrusion（行李箱進入限制區）

ROI 設定重點：
  - 以地面標線建立虛擬電子圍籬
  - 用 scripts/setup_roi.py 繪製 line（警戒線）與 zone（限制區域）

使用 Camera C（月台模擬區域）。

用法：
    python src/run_space_c.py
    python src/run_space_c.py --source data/demo_videos/camera_c.mp4
    python src/run_space_c.py --source rtsp://...
    python src/run_space_c.py --source 0
"""

import argparse
import sys
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
CLASS_LARGE_OBJECT = [28]   # suitcase（COCO）；可擴充至 [24, 26, 28]

CAMERA_ID = "camera_c"
ROI_RECORDS = "configs/roi_records.json"
CONFIG_PATH = "configs/cameras.yaml"


def _draw_intrusion_highlight(frame: np.ndarray, det: dict,
                              label: str, color=(0, 0, 255)):
    """對入侵目標加重標示（粗框 + 閃爍感）。"""
    x1, y1, x2, y2 = det["bbox"]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    cv2.putText(frame, f"! {label}", (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def run(source=None):
    cfg = load_yaml(CONFIG_PATH)

    cam_cfg_list = [c for c in cfg["cameras"] if c["id"] == CAMERA_ID]
    if not cam_cfg_list:
        log("WARN", f"cameras.yaml 中找不到 {CAMERA_ID}，使用預設值")
        cam_cfg = {"id": CAMERA_ID, "display_scale": 0.7}
    else:
        cam_cfg = cam_cfg_list[0]

    det_cfg = cfg["detector"]
    out_cfg = cfg["output"]

    src = source if source is not None else cam_cfg.get("source")
    fallback = None if source is not None else cam_cfg.get("fallback")
    display_scale = cam_cfg.get("display_scale", 0.7)
    large_classes = cam_cfg.get("large_object_classes", CLASS_LARGE_OBJECT)

    log("INFO", f"[Space C] 啟動  source={src}")

    # 啟動前自動 ROI 檢查（Space C 需要 zone + line）
    ensure_roi(CAMERA_ID,
               source=src,
               fallback=fallback,
               records_path=ROI_RECORDS,
               scene_name="Space C",
               expected_types=["zone", "line"])

    reader = RTSPReader(src, fallback=fallback)
    if not reader.open():
        return

    pre = Preprocessor.from_config(det_cfg.get("preprocess", {}))
    if not pre.is_noop:
        log("INFO", f"[Space C] 前處理已啟用: {det_cfg.get('preprocess')}")

    # 人員偵測器
    person_detector = Detector(
        det_cfg["model"], conf=det_cfg.get("conf", 0.4),
        device=det_cfg.get("device", "cpu"),
        target_classes=CLASS_PERSON,
        imgsz=det_cfg.get("imgsz", 640),
        preprocessor=pre,
    )
    # 大型物件偵測器（行李箱等）— 共用同一個前處理實例
    object_detector = Detector(
        det_cfg["model"], conf=det_cfg.get("conf", 0.35),
        device=det_cfg.get("device", "cpu"),
        target_classes=large_classes,
        imgsz=det_cfg.get("imgsz", 640),
        preprocessor=pre,
    )

    person_tracker = CentroidTracker(max_disappeared=30)
    object_tracker = CentroidTracker(max_disappeared=40)
    roi = ROIEngine(CAMERA_ID, ROI_RECORDS)
    events = EventManager(
        CAMERA_ID,
        snapshot_dir=out_cfg.get("snapshot_dir", "data/snapshots"),
        log_dir=out_cfg.get("log_dir", "data/logs"),
        save_snapshots=out_cfg.get("save_snapshots", True),
    )

    if not roi.zones and not roi.lines:
        log("WARN", "[Space C] 尚無 ROI 設定！請先執行：")
        log("WARN", "  python scripts/setup_roi.py --camera camera_c --source <影像> --type zone")
        log("WARN", "  python scripts/setup_roi.py --camera camera_c --source <影像> --type line")

    log("INFO", f"[Space C] zones={len(roi.zones)}, lines={len(roi.lines)}")

    active_alerts: list[str] = []

    while reader.is_opened():
        ret, frame = reader.read()
        if not ret:
            break

        roi.draw(frame)

        # ── 偵測與追蹤 ────────────────────────────────────────────────────────
        person_dets = person_detector.detect(frame)
        object_dets = object_detector.detect(frame)

        # Space C：不限制在 ROI 內才追蹤，但事件只在 ROI 相關時觸發
        tracked_persons = person_tracker.update(person_dets)
        tracked_objects = object_tracker.update(object_dets)

        draw_detections(frame, person_dets, color=(0, 220, 0))
        draw_detections(frame, object_dets, color=(0, 165, 255))
        draw_tracked(frame, tracked_persons)

        active_alerts.clear()

        # ── 規則 1：人員跨越警戒線 ────────────────────────────────────────────
        for obj_id, obj in tracked_persons.items():
            cx, cy = obj["cx"], obj["cy"]
            conf = obj["det"].get("conf", 0.5)

            for line_label in roi.check_line_crossing(obj_id, cx, cy):
                triggered = events.trigger(
                    event_type="line_crossing",
                    roi_id=line_label,
                    severity="high",
                    confidence=conf,
                    frame=frame,
                )
                if triggered:
                    active_alerts.append(f"LINE CROSS: person ID:{obj_id} → {line_label}")
                    _draw_intrusion_highlight(frame, obj["det"],
                                             f"CROSS {line_label}", (0, 0, 255))

        # ── 規則 2：人員進入限制區域（zone intrusion）────────────────────────
        for obj_id, obj in tracked_persons.items():
            cx, cy = obj["cx"], obj["cy"]
            conf = obj["det"].get("conf", 0.5)
            zone_labels = roi.get_zone_labels(cx, cy)
            for zone_label in zone_labels:
                triggered = events.trigger(
                    event_type="zone_intrusion",
                    roi_id=zone_label,
                    severity="high",
                    confidence=conf,
                    frame=frame,
                )
                if triggered:
                    active_alerts.append(f"INTRUSION: person ID:{obj_id} in {zone_label}")
                    _draw_intrusion_highlight(frame, obj["det"],
                                             f"INTRUSION {zone_label}", (0, 0, 200))

        # ── 規則 3：大型物件跨線 / 進入限制區域 ──────────────────────────────
        for obj_id, obj in tracked_objects.items():
            cx, cy = obj["cx"], obj["cy"]
            conf = obj["det"].get("conf", 0.5)
            label = obj["det"].get("label", "object")

            # 跨線
            for line_label in roi.check_line_crossing(
                    f"obj_{obj_id}", cx, cy):   # type: ignore[arg-type]
                triggered = events.trigger(
                    event_type="large_object_line_crossing",
                    roi_id=line_label,
                    severity="high",
                    confidence=conf,
                    frame=frame,
                )
                if triggered:
                    active_alerts.append(
                        f"OBJ CROSS: {label} ID:{obj_id} → {line_label}")
                    _draw_intrusion_highlight(frame, obj["det"],
                                             f"OBJ CROSS", (0, 80, 255))

            # 區域入侵
            zone_labels = roi.get_zone_labels(cx, cy)
            for zone_label in zone_labels:
                triggered = events.trigger(
                    event_type="large_object_intrusion",
                    roi_id=zone_label,
                    severity="high",
                    confidence=conf,
                    frame=frame,
                )
                if triggered:
                    active_alerts.append(
                        f"OBJ INTRUSION: {label} ID:{obj_id} in {zone_label}")
                    _draw_intrusion_highlight(frame, obj["det"],
                                             f"OBJ IN {zone_label}", (0, 80, 255))

        if active_alerts:
            draw_alert_bar(frame, active_alerts[0], color=(0, 0, 180))

        # 統計顯示
        info = f"Persons: {len(tracked_persons)}  Objects: {len(tracked_objects)}"
        cv2.putText(frame, info, (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        preview = cv2.resize(frame, None, fx=display_scale, fy=display_scale)
        cv2.imshow("CSAS PoC — Space C (月台)", preview)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    reader.release()
    cv2.destroyAllWindows()
    log("INFO", "[Space C] 已停止")


def main():
    parser = argparse.ArgumentParser(description="Space C — 月台模擬區域")
    parser.add_argument("--source", default=None,
                        help="影像來源：影片路徑 / RTSP URL / webcam index")
    args = parser.parse_args()
    src = int(args.source) if args.source and args.source.isdigit() else args.source
    run(source=src)


if __name__ == "__main__":
    main()
