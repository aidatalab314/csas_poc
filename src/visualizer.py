import cv2
import numpy as np


def draw_detections(frame: np.ndarray, detections: list[dict],
                    color: tuple = (0, 255, 0)):
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['label']} {det['conf']:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.circle(frame, (det["cx"], det["cy"]), 4, color, -1)
        cv2.putText(frame, label, (x1, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)


def draw_tracked(frame: np.ndarray, tracked: dict,
                 dwell_threshold: float = 0.0):
    for obj_id, obj in tracked.items():
        cx, cy = obj["cx"], obj["cy"]
        dwell = obj["dwell_seconds"]
        over_limit = dwell_threshold > 0 and dwell >= dwell_threshold
        color = (0, 0, 255) if over_limit else (255, 180, 0)
        label = f"ID:{obj_id} {dwell:.1f}s"
        cv2.circle(frame, (cx, cy), 8, color, -1)
        cv2.putText(frame, label, (cx + 10, cy - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def draw_alert_bar(frame: np.ndarray, text: str,
                   color: tuple = (0, 0, 200)):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 48), color, -1)
    cv2.putText(frame, text, (10, 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
