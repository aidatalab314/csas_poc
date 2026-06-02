"""
互動式 ROI 設定工具（CSAS PoC）。
以 camera_id 作為 key，支援 zone（多邊形）與 line（跨線）兩種類型。

用法：
    python scripts/setup_roi.py --camera camera_a --source data/demo_videos/camera_a.mp4
    python scripts/setup_roi.py --camera camera_a --source 0              # USB webcam
    python scripts/setup_roi.py --camera camera_a --source <RTSP URL>
    python scripts/setup_roi.py --camera camera_a --source ... --type line  # 繪製跨線
    python scripts/setup_roi.py --camera camera_a --reset               # 清除後重新繪製
    python scripts/setup_roi.py --list                                  # 列出所有 ROI 紀錄
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.roi_engine import draw_roi_interactive, load_roi_records, save_roi_records

RECORDS = "configs/roi_records.json"


def cmd_list():
    records = load_roi_records(RECORDS)
    if not records:
        print("[INFO] 目前沒有任何 ROI 紀錄。")
        return
    print(f"[INFO] 共 {len(records)} 個攝影機 ROI 紀錄：")
    for cam_id, rois in records.items():
        zones = [r for r in rois if r.get("type") != "line"]
        lines = [r for r in rois if r.get("type") == "line"]
        print(f"  {cam_id}: {len(zones)} zone(s), {len(lines)} line(s)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=str, default=None, help="camera id")
    parser.add_argument("--source", type=str, default=None,
                        help="影像來源：影片路徑 / RTSP URL / webcam index")
    parser.add_argument("--type", choices=["zone", "line"], default="zone",
                        help="ROI 類型：zone（多邊形）或 line（跨線）")
    parser.add_argument("--reset", action="store_true",
                        help="清除該 camera 的所有 ROI 後重新繪製")
    parser.add_argument("--list", action="store_true",
                        help="列出所有已有 ROI 紀錄")
    args = parser.parse_args()

    if args.list:
        cmd_list()
        return

    if not args.camera or not args.source:
        parser.print_help()
        return

    if args.reset:
        records = load_roi_records(RECORDS)
        records.pop(args.camera, None)
        import json
        with open(RECORDS, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print(f"[ROI] 已清除 {args.camera} 的 ROI 紀錄")

    source = int(args.source) if args.source.isdigit() else args.source
    rois = draw_roi_interactive(source, args.camera, roi_type=args.type)

    if not rois:
        print("[WARN] 未確認任何 ROI，不儲存。")
        return

    save_roi_records(args.camera, rois, RECORDS)


if __name__ == "__main__":
    main()
