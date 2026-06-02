"""
python -m pytest tests/test_roi_engine.py -v
"""
import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.roi_engine import ROIEngine


def _make_records(tmp_path: Path, camera_id: str) -> str:
    records = {
        camera_id: [
            {
                "id": "zone_0", "label": "Zone 0", "type": "zone",
                "color": [0, 255, 255],
                "points": [[0, 0], [200, 0], [200, 200], [0, 200]],
            },
            {
                "id": "line_0", "label": "Line 0", "type": "line",
                "color": [255, 0, 255],
                "points": [[100, 0], [100, 300]],
            },
        ]
    }
    p = tmp_path / "roi_records.json"
    p.write_text(json.dumps(records))
    return str(p)


def test_zone_inside(tmp_path):
    records = _make_records(tmp_path, "cam")
    roi = ROIEngine("cam", records)
    assert roi.is_in_any_zone(100, 100)


def test_zone_outside(tmp_path):
    records = _make_records(tmp_path, "cam")
    roi = ROIEngine("cam", records)
    assert not roi.is_in_any_zone(300, 300)


def test_no_zone_returns_true(tmp_path):
    records = str(tmp_path / "empty.json")
    Path(records).write_text("{}")
    roi = ROIEngine("cam", records)
    assert roi.is_in_any_zone(999, 999)


def test_line_crossing(tmp_path):
    records = _make_records(tmp_path, "cam")
    roi = ROIEngine("cam", records)
    # 從線左側移到右側
    roi.check_line_crossing(1, 50, 150)   # left side
    crossed = roi.check_line_crossing(1, 150, 150)  # right side
    assert "Line 0" in crossed


def test_no_crossing_same_side(tmp_path):
    records = _make_records(tmp_path, "cam")
    roi = ROIEngine("cam", records)
    roi.check_line_crossing(1, 50, 150)
    crossed = roi.check_line_crossing(1, 60, 150)
    assert crossed == []
