"""
Space A — 車站大廳 / 開放式通道（多攝影機版）
=============================================
偵測項目：
  1. 區域人流密度     → crowd_density_alert
  2. 滯留物偵測       → abandoned_object
  3. 異常移動偵測     → abnormal_movement

啟動流程：
  1. 自動檢查各攝影機是否有 ROI 設定，無則引導互動設定
  2. 每台攝影機獨立執行緒（各自 Detector / Tracker / ROI / EventManager）
  3. 主執行緒以分割畫面（split-screen）單視窗並排顯示

ReID 跨攝影機追蹤保留至第二階段。

用法：
    # 單台（預設 camera_a）
    python src/run_space_a.py

    # 單台 + 指定影像來源
    python src/run_space_a.py --cameras camera_a --source 0
    python src/run_space_a.py --cameras camera_a --source data/demo_videos/hall.mp4
    python src/run_space_a.py --cameras camera_a --source rtsp://root:root@192.168.6.90/cam1/h264

    # 雙攝影機同時執行（split-screen 顯示）
    python src/run_space_a.py --cameras camera_a,camera_b
"""

import argparse
import sys
import math
import queue
import threading
import time
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

CLASS_PERSON  = [0]
CLASS_OBJECTS = [24, 26, 28]   # backpack, handbag, suitcase

ROI_RECORDS = "configs/roi_records.json"
CONFIG_PATH = "configs/cameras.yaml"
PANEL_H     = 540              # split-screen 每路攝影機的顯示高度（px）

_DONE = object()               # sentinel：通知主執行緒此路 worker 已結束


# ── 工具函式 ──────────────────────────────────────────────────────────────────

def _nearest_person_dist(cx: int, cy: int, persons: list[dict]) -> float:
    if not persons:
        return float("inf")
    return min(math.hypot(p["cx"] - cx, p["cy"] - cy) for p in persons)


def _get(cam_cfg: dict, space_a_cfg: dict, key: str, default):
    """攝影機設定 → 全域 space_a 預設 → hardcode 預設。"""
    return cam_cfg.get(key, space_a_cfg.get(key, default))


def _make_panel(frame: np.ndarray, label: str) -> np.ndarray:
    """將 frame 縮放至 PANEL_H，並在頂端貼上攝影機 label。"""
    h, w = frame.shape[:2]
    scale = PANEL_H / h
    panel = cv2.resize(frame, (int(w * scale), PANEL_H))
    cv2.rectangle(panel, (0, 0), (panel.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(panel, label, (8, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    return panel


# ── 單台攝影機 worker（執行緒）────────────────────────────────────────────────

def _camera_worker(cam_cfg: dict, det_cfg: dict, out_cfg: dict,
                   space_a_cfg: dict,
                   frame_q: queue.Queue,
                   stop: threading.Event):
    camera_id = cam_cfg["id"]
    tag = f"[Space A | {camera_id}]"

    crowd_threshold = _get(cam_cfg, space_a_cfg, "crowd_alert_count",        5)
    abandoned_secs  = _get(cam_cfg, space_a_cfg, "abandoned_alert_seconds",  15.0)
    proximity_px    = _get(cam_cfg, space_a_cfg, "abandoned_proximity_px",   120)
    speed_px        = _get(cam_cfg, space_a_cfg, "speed_alert_px_per_frame", 20)
    speed_count     = _get(cam_cfg, space_a_cfg, "speed_alert_person_count", 2)

    log("INFO", f"{tag} 啟動")

    reader = RTSPReader(cam_cfg.get("source"), fallback=cam_cfg.get("fallback"))
    if not reader.open():
        frame_q.put(_DONE)
        return

    pre = Preprocessor.from_config(det_cfg.get("preprocess", {}))
    if not pre.is_noop:
        log("INFO", f"{tag} 前處理已啟用")

    # ── 優化①：單次 YOLO 推論同時偵測人員與物件 ─────────────────────────────
    detector = Detector(
        det_cfg["model"], conf=det_cfg.get("conf", 0.4),
        device=det_cfg.get("device", "cpu"),
        target_classes=CLASS_PERSON + CLASS_OBJECTS,   # 一次推論，結果再拆分
        imgsz=det_cfg.get("imgsz", 640),
        preprocessor=pre,
    )

    person_tracker = CentroidTracker(max_disappeared=30)
    object_tracker = CentroidTracker(max_disappeared=60)
    roi    = ROIEngine(camera_id, ROI_RECORDS)
    events = EventManager(
        camera_id,
        snapshot_dir=out_cfg.get("snapshot_dir", "data/snapshots"),
        log_dir=out_cfg.get("log_dir",            "data/logs"),
        save_snapshots=out_cfg.get("save_snapshots", True),
    )

    log("INFO", f"{tag} zones={len(roi.zones)}, lines={len(roi.lines)}")

    # CUDA warmup（用實際解析度觸發完整 JIT 編譯，避免第一幀卡住 queue）
    w, h = reader.get_size()
    log("INFO", f"{tag} CUDA warmup ({w}×{h})...")
    _t0 = time.monotonic()
    detector.detect(np.zeros((h, w, 3), dtype=np.uint8))
    log("INFO", f"{tag} warmup 完成 ({time.monotonic()-_t0:.1f}s)，開始接收畫面")

    # ── 優化②：frame skip ────────────────────────────────────────────────────
    skip_n        = max(1, det_cfg.get("inference_skip_frames", 1))
    frame_count   = 0
    cached_persons: list[dict] = []
    cached_objects: list[dict] = []
    tracked_persons: dict = {}
    tracked_objects: dict = {}

    # ── FPS 計量 ──────────────────────────────────────────────────────────────
    fps_t0     = time.monotonic()
    fps_frames = 0
    fps_val    = 0.0

    prev_pos: dict[int, tuple[int, int]] = {}

    while not stop.is_set() and reader.is_opened():
        ret, frame = reader.read()
        if not ret:
            break

        frame_count += 1
        fps_frames  += 1

        # 第一幀存檔確認內容（debug 用，確認後可移除）
        if frame_count == 1:
            cv2.imwrite('/tmp/debug_frame_raw.jpg', frame)
            log("INFO", f"{tag} 第一幀已儲存 /tmp/debug_frame_raw.jpg  shape={frame.shape} max={frame.max()}")

        # FPS 每 30 幀更新一次
        if fps_frames == 30:
            fps_val    = 30 / (time.monotonic() - fps_t0)
            fps_t0     = time.monotonic()
            fps_frames = 0

        roi.draw(frame)

        # ── 推論（skip 非推論幀，沿用上一次結果）────────────────────────────
        if frame_count % skip_n == 0:
            all_dets      = detector.detect(frame)
            cached_persons = [d for d in all_dets if d["class_id"] == 0]
            cached_objects = [d for d in all_dets if d["class_id"] in (24, 26, 28)]

            person_in_roi = [d for d in cached_persons
                             if roi.is_in_any_zone(d["cx"], d["cy"])]
            object_in_roi = [d for d in cached_objects
                             if roi.is_in_any_zone(d["cx"], d["cy"])]

            tracked_persons = person_tracker.update(person_in_roi)
            tracked_objects = object_tracker.update(object_in_roi)
        else:
            person_in_roi = [d for d in cached_persons
                             if roi.is_in_any_zone(d["cx"], d["cy"])]
            object_in_roi = [d for d in cached_objects
                             if roi.is_in_any_zone(d["cx"], d["cy"])]

        draw_detections(frame, person_in_roi, color=(0, 255, 0))
        draw_detections(frame, object_in_roi, color=(0, 165, 255))
        draw_tracked(frame, tracked_persons)

        # ── 計算各 zone 人數 ──────────────────────────────────────────────────
        if roi.zones:
            zone_counts: dict[str, int] = {
                zone["label"]: sum(
                    1 for obj in tracked_persons.values()
                    if zone["label"] in roi.get_zone_labels(obj["cx"], obj["cy"])
                )
                for zone in roi.zones
            }
            people_str = "  ".join(f"{lbl}:{cnt}" for lbl, cnt in zone_counts.items())
        else:
            zone_counts = {"full_frame": len(tracked_persons)}
            people_str = f"People:{len(tracked_persons)}"

        # 狀態列：各 zone 人數 + FPS + skip 模式
        skip_label = f"  skip:{skip_n}" if skip_n > 1 else ""
        status = f"{people_str}  FPS:{fps_val:.1f}{skip_label}"
        cv2.putText(frame, status, (10, frame.shape[0] - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        active_alerts: list[str] = []

        # 規則 1：人流密度（逐 zone 判斷，使用實際 zone 標籤）
        for zone_label, count in zone_counts.items():
            if count >= crowd_threshold:
                events.trigger("crowd_density_alert", zone_label, "medium", 1.0, frame)
                active_alerts.append(f"CROWD {zone_label}: {count} persons")

        # 規則 2：滯留物
        for obj_id, obj in tracked_objects.items():
            cx, cy = obj["cx"], obj["cy"]
            dwell  = obj["dwell_seconds"]
            label  = obj["det"].get("label", "object")
            conf   = obj["det"].get("conf", 0.5)
            x1, y1, x2, y2 = obj["det"]["bbox"]
            color = (0, 50, 255) if dwell >= abandoned_secs else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {dwell:.0f}s",
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            if dwell >= abandoned_secs:
                if _nearest_person_dist(cx, cy, person_in_roi) > proximity_px:
                    zone_labels = roi.get_zone_labels(cx, cy) or ["zone_a"]
                    if events.trigger("abandoned_object", zone_labels[0],
                                      "high", conf, frame):
                        active_alerts.append(f"ABANDONED: {label} ID:{obj_id}")

        # 規則 3：異常移動
        fast: list[int] = []
        for obj_id, obj in tracked_persons.items():
            cx, cy = obj["cx"], obj["cy"]
            prev = prev_pos.get(obj_id)
            if prev and math.hypot(cx - prev[0], cy - prev[1]) > speed_px:
                fast.append(obj_id)
                cv2.arrowedLine(frame, prev, (cx, cy), (0, 0, 255), 2)
            prev_pos[obj_id] = (cx, cy)
        for gone_id in list(prev_pos):
            if gone_id not in tracked_persons:
                del prev_pos[gone_id]
        if len(fast) >= speed_count:
            # 取快速移動者所在的 zone 標籤（取聯集）
            fast_zones: set[str] = set()
            for obj_id in fast:
                if obj_id in tracked_persons:
                    obj = tracked_persons[obj_id]
                    labels = roi.get_zone_labels(obj["cx"], obj["cy"])
                    fast_zones.update(labels if labels else ["full_frame"])
            for zone_label in (fast_zones or {"full_frame"}):
                events.trigger("abnormal_movement", zone_label, "medium", 0.8, frame)
            active_alerts.append(f"FAST MOVE: {len(fast)} persons")

        if active_alerts:
            draw_alert_bar(frame, active_alerts[0])

        try:
            frame_q.put_nowait(frame)
        except queue.Full:
            pass

    reader.release()
    frame_q.put(_DONE)          # 保證 sentinel 可送達（blocking）
    log("INFO", f"{tag} 已停止")


# ── 主函式 ────────────────────────────────────────────────────────────────────

def run(camera_ids: list[str] | None = None, source_override=None):
    cfg         = load_yaml(CONFIG_PATH)
    det_cfg     = cfg["detector"]
    out_cfg     = cfg["output"]
    space_a_cfg = cfg.get("space_a", {})

    if camera_ids is None:
        camera_ids = ["camera_a"]

    cam_map   = {c["id"]: c for c in cfg["cameras"]}
    valid_ids = [cid for cid in camera_ids if cid in cam_map]

    if not valid_ids:
        log("ERROR", f"cameras.yaml 中找不到：{camera_ids}")
        return

    # 單台模式允許 --source 覆蓋
    if source_override and len(valid_ids) == 1:
        cid = valid_ids[0]
        cam_map[cid] = dict(cam_map[cid])
        cam_map[cid]["source"]  = source_override
        cam_map[cid].pop("fallback", None)

    # ── 啟動前：自動 ROI 檢查（主執行緒，可開 cv2 視窗）─────────────────────
    for cid in valid_ids:
        ensure_roi(cid,
                   source=cam_map[cid].get("source"),
                   fallback=cam_map[cid].get("fallback"),
                   records_path=ROI_RECORDS,
                   scene_name="Space A",
                   expected_types=["zone"])

    # ── 建立 frame queue 與 stop event ───────────────────────────────────────
    frame_qs: dict[str, queue.Queue] = {
        cid: queue.Queue(maxsize=4) for cid in valid_ids
    }
    stop = threading.Event()

    # ── 啟動 camera worker threads ───────────────────────────────────────────
    threads: list[threading.Thread] = []
    for cid in valid_ids:
        t = threading.Thread(
            target=_camera_worker,
            args=(cam_map[cid], det_cfg, out_cfg, space_a_cfg,
                  frame_qs[cid], stop),
            name=f"SpaceA-{cid}",
            daemon=True,
        )
        t.start()
        threads.append(t)

    log("INFO", f"[Space A] 執行中：{valid_ids}  |  按 Q / ESC 結束")

    # ── 主執行緒：split-screen 顯示 ──────────────────────────────────────────
    WIN_TITLE = "CSAS PoC — Space A"
    latest: dict[str, np.ndarray | None] = {cid: None for cid in valid_ids}
    finished: set[str] = set()

    while len(finished) < len(valid_ids):
        for cid in valid_ids:
            if cid in finished:
                continue
            # 排空 queue，只保留最新一幀
            last_frame = None
            got_done   = False
            while True:
                try:
                    item = frame_qs[cid].get_nowait()
                    if item is _DONE:
                        got_done = True
                        break
                    last_frame = item          # 持續取直到 queue 空
                except queue.Empty:
                    break

            if last_frame is not None:
                latest[cid] = last_frame
            if got_done:
                finished.add(cid)

        # 組合 split-screen
        panels = [
            _make_panel(latest[cid], cid)
            for cid in valid_ids
            if latest[cid] is not None
        ]
        if panels:
            combined = np.hstack(panels) if len(panels) > 1 else panels[0]
            cv2.imshow(WIN_TITLE, combined)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            log("INFO", "[Space A] 使用者中止")
            stop.set()
            break

    stop.set()
    for t in threads:
        t.join(timeout=5)
    cv2.destroyAllWindows()
    log("INFO", "[Space A] 所有攝影機已停止")


def main():
    parser = argparse.ArgumentParser(description="Space A — 車站大廳 / 開放式通道")
    parser.add_argument(
        "--cameras", default="camera_a",
        help="攝影機 ID，多台以逗號分隔（預設：camera_a）",
    )
    parser.add_argument(
        "--source", default=None,
        help="覆蓋影像來源（僅限單台）：影片路徑 / RTSP URL / webcam index",
    )
    args = parser.parse_args()

    camera_ids = [c.strip() for c in args.cameras.split(",")]
    src = int(args.source) if args.source and args.source.isdigit() else args.source

    if src and len(camera_ids) > 1:
        log("WARN", "--source 僅支援單台模式，多台請設定 cameras.yaml")
        src = None

    run(camera_ids=camera_ids, source_override=src)


if __name__ == "__main__":
    main()
