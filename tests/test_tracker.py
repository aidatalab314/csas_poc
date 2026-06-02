"""
python -m pytest tests/test_tracker.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tracker import CentroidTracker


def _det(cx, cy, label="person", conf=0.9):
    x1, y1 = cx - 20, cy - 40
    x2, y2 = cx + 20, cy + 40
    return {"class_id": 0, "label": label, "conf": conf,
            "bbox": (x1, y1, x2, y2), "cx": cx, "cy": cy}


def test_register_new_objects():
    t = CentroidTracker()
    tracked = t.update([_det(100, 100), _det(300, 300)])
    assert len(tracked) == 2


def test_consistent_ids():
    t = CentroidTracker()
    t.update([_det(100, 100)])
    tracked = t.update([_det(105, 102)])
    assert len(tracked) == 1
    assert 0 in tracked


def test_disappeared_deregisters():
    t = CentroidTracker(max_disappeared=2)
    t.update([_det(100, 100)])
    t.update([])
    t.update([])
    tracked = t.update([])
    assert len(tracked) == 0


def test_dwell_time_increases():
    import time
    t = CentroidTracker()
    t.update([_det(100, 100)])
    time.sleep(0.05)
    tracked = t.update([_det(101, 100)])
    obj = list(tracked.values())[0]
    assert obj["dwell_seconds"] >= 0.05
