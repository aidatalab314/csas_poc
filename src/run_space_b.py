"""
Space B — 樓梯 / 狹窄通道
==========================
偵測項目：
  1. 群眾恐慌性移動   → N 人同時快速移動觸發 crowd_rush
  2. 通道擁擠         → 人數超過門檻觸發 congestion_alert
  3. 聲音事件偵測     → [MVP 佔位] YOHO 音訊模型預留位置

使用 Camera B（樓梯 / 狹窄通道）。
偵測參數讀取順序：camera_b 個別設定 → space_b 全域預設 → hardcode 預設。

用法：
    python src/run_space_b.py
    python src/run_space_b.py --source data/demo_videos/camera_b.mp4
    python src/run_space_b.py --source rtsp://root:root@192.168.6.91/cam1/h264
    python src/run_space_b.py --source 0
"""

import argparse
import sys
import math
import time
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rtsp_reader import RTSPReader
from src.detector import Detector
from src.preprocessor import Preprocessor
from src.tracker import CentroidTracker
from src.roi_engine import ROIEngine, ensure_roi, draw_roi_for_test
from src.event_manager import EventManager
from src.visualizer import draw_detections, draw_tracked, draw_alert_bar
from src.utils import load_yaml, log

CLASS_PERSON = [0]

CAMERA_ID   = "camera_b"
ROI_RECORDS = "configs/roi_records.json"
CONFIG_PATH = "configs/cameras.yaml"


def _get(cam_cfg: dict, space_b_cfg: dict, key: str, default):
    """攝影機設定 → 全域 space_b 預設 → hardcode 預設。"""
    return cam_cfg.get(key, space_b_cfg.get(key, default))


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
    pass


def run(source=None, mode: str = "dev"):
    cfg         = load_yaml(CONFIG_PATH)
    cam_cfg     = next(c for c in cfg["cameras"] if c["id"] == CAMERA_ID)
    det_cfg     = cfg["detector"]
    out_cfg     = cfg["output"]
    space_b_cfg = cfg.get("space_b", {})

    src           = source if source is not None else cam_cfg.get("source")
    fallback      = None if source is not None else cam_cfg.get("fallback")
    display_scale = cfg.get("display", {}).get("scale", 0.7)

    rush_speed       = _get(cam_cfg, space_b_cfg, "rush_speed_px_per_frame", 25)
    rush_count       = _get(cam_cfg, space_b_cfg, "rush_person_count",        3)
    congestion_count = _get(cam_cfg, space_b_cfg, "congestion_alert_count",   8)
    skip_n           = max(1, det_cfg.get("inference_skip_frames", 1))

    log("INFO", f"[Space B] 啟動 [mode={mode}]  source={src}")
    log("INFO", "[Space B] 聲音事件偵測：MVP 版本為佔位模式（YOHO 尚未整合）")

    if source is not None:
        log("INFO", "[Space B] 測試影片模式：ROI 每次重新繪製，不寫入 roi_records.json")
        test_rois = draw_roi_for_test(src, CAMERA_ID, expected_types=["zone"])
    else:
        test_rois = None
        ensure_roi(CAMERA_ID,
                   source=src,
                   fallback=fallback,
                   records_path=ROI_RECORDS,
                   scene_name="Space B",
                   expected_types=["zone"])

    reader = RTSPReader(src, fallback=fallback)
    if not reader.open():
        return

    writer = None
    if source is not None and mode == "dev":
        w_vid, h_vid = reader.get_size()
        stem     = Path(str(src)).stem
        ts       = time.strftime("%Y%m%d_%H%M%S")
        out_path = Path("data/test_recordings") / f"{stem}_{ts}.mp4"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fourcc   = cv2.VideoWriter_fourcc(*"mp4v")
        writer   = cv2.VideoWriter(str(out_path), fourcc, reader.get_fps(), (w_vid, h_vid))
        log("INFO", f"[Space B] 測試錄影輸出：{out_path}")

    pre = Preprocessor.from_config(det_cfg.get("preprocess", {}))
    if not pre.is_noop:
        log("INFO", f"[Space B] 前處理已啟用")

    detector = Detector(
        det_cfg["model"], conf=det_cfg.get("conf", 0.4),
        device=det_cfg.get("device", "cpu"),
        target_classes=CLASS_PERSON,
        imgsz=det_cfg.get("imgsz", 640),
        preprocessor=pre,
    )

    tracker = CentroidTracker(max_disappeared=25)
    roi = (ROIEngine.from_rois(CAMERA_ID, test_rois)
           if test_rois is not None
           else ROIEngine(CAMERA_ID, ROI_RECORDS))
    events  = EventManager(
        CAMERA_ID,
        snapshot_dir=out_cfg.get("snapshot_dir", "data/snapshots"),
        log_dir=out_cfg.get("log_dir",            "data/logs"),
        save_snapshots=out_cfg.get("save_snapshots", True),
    )

    log("INFO", f"[Space B] zones={len(roi.zones)}, lines={len(roi.lines)}")

    prev_pos: dict[int, tuple[int, int]] = {}
    frame_count  = 0
    cached_dets: list[dict] = []
    tracked: dict = {}
    fps_t0     = time.monotonic()
    fps_frames = 0
    fps_val    = 0.0

    while reader.is_opened():
        ret, frame = reader.read()
        if not ret:
            break

        frame_count += 1
        fps_frames  += 1
        if fps_frames == 30:
            fps_val    = 30 / (time.monotonic() - fps_t0)
            fps_t0     = time.monotonic()
            fps_frames = 0

        # ── 推論（跳幀，沿用快取結果）──────────────────────────────────────────
        if frame_count % skip_n == 0:
            dets        = detector.detect(frame)
            cached_dets = [d for d in dets if roi.is_in_any_zone(d["cx"], d["cy"])]
            tracked     = tracker.update(cached_dets)

        # 狀態字串
        if roi.zones:
            zone_str = "  ".join(
                f"{z['label']}:{sum(1 for obj in tracked.values() if z['label'] in roi.get_zone_labels(obj['cx'], obj['cy']))}"
                for z in roi.zones
            )
        else:
            zone_str = f"People:{len(tracked)}"
        skip_label = f"  skip:{skip_n}" if skip_n > 1 else ""
        status = f"{zone_str}  FPS:{fps_val:.1f}{skip_label}"

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

        roi_labels    = [z["label"] for z in roi.zones] or ["zone_b"]
        active_alerts: list[str] = []

        # snapshot 用的標注幀：ROI + 偵測框 + 追蹤 ID + 速度 overlay 先畫上去
        snap_frame = frame.copy()
        roi.draw(snap_frame)
        draw_detections(snap_frame, cached_dets)
        draw_tracked(snap_frame, tracked)
        _draw_speed_overlay(snap_frame, current_speeds, tracked, rush_speed)

        # ── 規則 1：群眾恐慌性移動 ────────────────────────────────────────────
        fast_persons = [oid for oid, spd in current_speeds.items() if spd > rush_speed]
        if len(fast_persons) >= rush_count:
            events.trigger("crowd_rush", roi_labels[0], "high",
                           min(1.0, len(fast_persons) / rush_count), snap_frame)
            active_alerts.append(f"CROWD RUSH {roi_labels[0]}: {len(fast_persons)} persons")

        # ── 規則 2：通道擁擠 ──────────────────────────────────────────────────
        if len(tracked) >= congestion_count:
            events.trigger("congestion_alert", roi_labels[0], "medium", 1.0, snap_frame)
            active_alerts.append(f"CONGESTION {roi_labels[0]}: {len(tracked)} persons")

        _audio_placeholder()

        # ── 作業模式：定期 log 狀態，警報即時輸出 ────────────────────────────
        if mode == "op":
            if fps_frames == 0:
                log("INFO", f"[Space B] {status}")
            for alert in active_alerts:
                log("WARN", f"[Space B] ALERT: {alert}")
            continue

        # ── 開發者模式：繪圖 + 顯示 ──────────────────────────────────────────
        roi.draw(frame)
        draw_detections(frame, cached_dets)
        draw_tracked(frame, tracked)
        _draw_speed_overlay(frame, current_speeds, tracked, rush_speed)
        cv2.putText(frame, status, (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        if active_alerts:
            draw_alert_bar(frame, active_alerts[0], color=(180, 0, 0))
        if writer is not None:
            writer.write(frame)

        preview = cv2.resize(frame, None, fx=display_scale, fy=display_scale)
        cv2.imshow("CSAS PoC — Space B (樓梯/通道)", preview)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break

    reader.release()
    if writer is not None:
        writer.release()
        log("INFO", f"[Space B] 測試錄影已儲存：{out_path}")
    if mode == "dev":
        cv2.destroyAllWindows()
    log("INFO", "[Space B] 已停止")


def main():
    parser = argparse.ArgumentParser(description="Space B — 樓梯 / 狹窄通道")
    parser.add_argument("--source", default=None,
                        help="影像來源：影片路徑 / RTSP URL / webcam index")
    parser.add_argument("--mode", default="dev", choices=["dev", "op"],
                        help="dev：顯示畫面；op：無畫面，僅 log 輸出")
    args = parser.parse_args()
    src = int(args.source) if args.source and args.source.isdigit() else args.source
    run(source=src, mode=args.mode)


if __name__ == "__main__":
    main()
