import json
import numpy as np
import cv2
from pathlib import Path


# ── 互動式繪製工具（改自 KMetro_cv/src/roi/roi_manager.py）─────────────────────

COLORS = [
    (0, 255, 255),
    (255, 0, 255),
    (0, 255, 0),
    (0, 165, 255),
    (255, 100, 0),
]


def draw_roi_interactive(source, camera_id: str, roi_type: str = "zone") -> list[dict]:
    """
    互動式 ROI 繪製工具。
    roi_type: "zone"（多邊形）或 "line"（跨線，只取前兩點）

    操作：
      左鍵       加點
      右鍵       刪除最後一點
      C          確認當前 ROI（zone ≥ 3 點，line = 2 點）
      R          重置當前未完成 ROI
      ESC / Q    儲存並結束
    """
    cap = cv2.VideoCapture(source if not str(source).isdigit() else int(source))
    ret, original = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"無法讀取影像來源: {source}")

    H, W = original.shape[:2]
    scale = min(1.0, 1280 / W)
    win = f"ROI Setup [{camera_id}] ({roi_type})"
    min_pts = 2 if roi_type == "line" else 3

    state = {"pts": [], "rois": []}

    def _color(idx):
        return COLORS[idx % len(COLORS)]

    def _redraw():
        frame = original.copy()

        for roi in state["rois"]:
            pts_arr = [list(p) for p in roi["points"]]
            color = tuple(roi["color"])
            if roi["type"] == "zone":
                poly = np.array(pts_arr, np.int32)
                overlay = frame.copy()
                cv2.fillPoly(overlay, [poly], color)
                result = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)
                np.copyto(frame, result)
                cv2.polylines(frame, [poly], True, color, 3)
                cv2.putText(frame, roi["label"], tuple(poly[0]),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
            else:
                p1, p2 = tuple(pts_arr[0]), tuple(pts_arr[1])
                cv2.line(frame, p1, p2, color, 3)
                mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
                cv2.putText(frame, roi["label"], mid,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        cur_color = _color(len(state["rois"]))
        pts = state["pts"]
        for pt in pts:
            cv2.circle(frame, pt, 7, cur_color, -1)
        if len(pts) >= 2:
            if roi_type == "zone":
                poly = np.array(pts, np.int32)
                if len(pts) >= 3:
                    overlay = frame.copy()
                    cv2.fillPoly(overlay, [poly], cur_color)
                    result = cv2.addWeighted(overlay, 0.25, frame, 0.75, 0)
                    np.copyto(frame, result)
                    cv2.polylines(frame, [poly], True, cur_color, 2)
                else:
                    cv2.polylines(frame, [poly], False, cur_color, 2)
            else:
                cv2.line(frame, pts[0], pts[1], cur_color, 3)

        tips = [
            "Left click : add point",
            "Right click: undo point",
            f"[C]        : confirm ROI (>={min_pts} pts)",
            "[R]        : reset current ROI",
            "[ESC/Q]    : save & quit",
            f"Type: {roi_type}  |  ROIs done: {len(state['rois'])}",
        ]
        for i, t in enumerate(tips):
            y = 28 + i * 24
            cv2.putText(frame, t, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
            cv2.putText(frame, t, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

        cv2.imshow(win, cv2.resize(frame, None, fx=scale, fy=scale))
        cv2.waitKey(1)

    def _mouse(event, x, y, flags, param):
        ox, oy = int(x / scale), int(y / scale)
        if event == cv2.EVENT_LBUTTONDOWN:
            if roi_type == "line" and len(state["pts"]) >= 2:
                return
            state["pts"].append((ox, oy))
            _redraw()
        elif event == cv2.EVENT_RBUTTONDOWN:
            if state["pts"]:
                state["pts"].pop()
                _redraw()

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, _mouse)
    _redraw()

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (ord('c'), ord('C')):
            if len(state["pts"]) >= min_pts:
                idx = len(state["rois"])
                pts_to_save = state["pts"][:2] if roi_type == "line" else state["pts"]
                state["rois"].append({
                    "id": f"{roi_type}_{idx}",
                    "label": f"{'Line' if roi_type == 'line' else 'Zone'} {idx}",
                    "type": roi_type,
                    "color": list(_color(idx)),
                    "points": [list(p) for p in pts_to_save],
                })
                state["pts"] = []
                _redraw()
                print(f"[ROI] {roi_type} {idx} confirmed")
            else:
                print(f"[ROI] 至少需要 {min_pts} 個點")

        elif key in (ord('r'), ord('R')):
            state["pts"] = []
            _redraw()

        elif key in (27, ord('q'), ord('Q')):
            if len(state["pts"]) >= min_pts:
                idx = len(state["rois"])
                pts_to_save = state["pts"][:2] if roi_type == "line" else state["pts"]
                state["rois"].append({
                    "id": f"{roi_type}_{idx}",
                    "label": f"{'Line' if roi_type == 'line' else 'Zone'} {idx}",
                    "type": roi_type,
                    "color": list(_color(idx)),
                    "points": [list(p) for p in pts_to_save],
                })
                print(f"[ROI] {roi_type} {idx} auto-confirmed on exit")
            break

    # 修正①：關閉視窗後 flush macOS 事件佇列，並提示使用者回到終端機
    cv2.destroyWindow(win)
    cv2.waitKey(500)
    print("\n" + "─" * 50)
    print("[ROI] 視窗已關閉，請回到此終端機繼續操作")
    print("─" * 50)
    return state["rois"]


def _try_draw_roi(source, fallback, camera_id: str, roi_type: str,
                  tag: str) -> list[dict]:
    """嘗試開啟 source 繪製 ROI，失敗則嘗試 fallback。"""
    for src, label in [(source, "主要"), (fallback, "備援")]:
        if src is None:
            continue
        try:
            return draw_roi_interactive(src, camera_id, roi_type=roi_type)
        except RuntimeError as e:
            print(f"{tag} {label}來源失敗：{e}")
    print(f"{tag} 無法開啟任何影像來源，跳過 ROI 設定")
    return []


def ensure_roi(camera_id: str, source,
               fallback=None,
               records_path: str = "configs/roi_records.json",
               scene_name: str = "",
               expected_types: list[str] | None = None) -> None:
    """
    啟動前自動檢查指定攝影機是否有對應場域的 ROI 設定。
    - 有紀錄 → 印出摘要，繼續執行。
    - 無紀錄 → 詢問是否立即設定；N 則以全幀（無圍籬）模式執行。

    fallback: RTSP 失敗時改用的備援來源（本地影片 / webcam index）
    expected_types: 此場域需要的 ROI 類型，例如 ["zone"] 或 ["zone", "line"]
    """
    tag = f"[ROI{' | ' + scene_name if scene_name else ''}]"
    records = load_roi_records(records_path)
    existing = records.get(camera_id, [])

    if existing:
        zones = [r for r in existing if r.get("type") != "line"]
        lines = [r for r in existing if r.get("type") == "line"]
        print(f"{tag} {camera_id}: 已有設定 — {len(zones)} zone, {len(lines)} line")
        return

    print(f"\n{tag} {camera_id}: 尚無 ROI 設定")
    if expected_types:
        print(f"{tag}   此場域建議類型：{', '.join(expected_types)}")
    print(f"{tag}   未設定時系統以全幀為偵測範圍（無圍籬模式）")

    try:
        ans = input(f"{tag} 是否現在設定 ROI？[Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"

    if ans not in ("y", "yes", ""):
        print(f"{tag} {camera_id}: 跳過，以全幀模式執行")
        return

    # 依序處理每種需要的 ROI 類型
    types_to_draw = expected_types[:] if expected_types else ["zone"]
    first = True
    for roi_type in types_to_draw:
        if not first:
            try:
                more = input(
                    f"{tag} 是否繼續設定 {roi_type}？[Y/n]: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if more not in ("y", "yes", ""):
                break
        first = False

        print(f"{tag} 開啟 {roi_type} 繪製視窗…")
        rois = _try_draw_roi(source, fallback, camera_id, roi_type, tag)
        if rois:
            save_roi_records(camera_id, rois, records_path)
        else:
            print(f"{tag} {camera_id} ({roi_type}): 未繪製任何 ROI")


def load_roi_records(records_path: str) -> dict:
    p = Path(records_path)
    if not p.exists():
        return {}
    with open(p) as f:
        data = {k: v for k, v in __import__('json').load(f).items()
                if not k.startswith("_")}
    return data


def save_roi_records(camera_id: str, rois: list[dict], records_path: str):
    """
    修正②：同類型 ROI 以新設定取代舊設定（而非累加）。
    - 新 zone → 取代舊 zone，保留舊 line
    - 新 line → 取代舊 line，保留舊 zone
    避免重複設定產生重疊 ROI。
    """
    if not rois:
        return
    p = Path(records_path)
    records = load_roi_records(records_path)
    existing = records.get(camera_id, [])

    new_types = {r.get("type", "zone") for r in rois}
    kept = [r for r in existing if r.get("type", "zone") not in new_types]
    records[camera_id] = kept + rois

    with open(p, "w") as f:
        __import__('json').dump(records, f, indent=2, ensure_ascii=False)
    print(f"[ROI] 已儲存 {len(rois)} 個 {'/'.join(new_types)} ROI"
          f" → {records_path}  (camera: {camera_id})")


# ── ROI 管理器 ─────────────────────────────────────────────────────────────────

class ROIEngine:
    """
    支援：
    - zone（多邊形）：區域入侵偵測、滯留時間過濾
    - line（線段）：跨線偵測（有方向感知）
    """

    def __init__(self, camera_id: str, records_path: str = "configs/roi_records.json"):
        self.camera_id = camera_id
        self.zones: list[dict] = []
        self.lines: list[dict] = []
        self._line_states: dict[tuple, int] = {}  # (obj_id, line_id) -> side
        self._load(records_path)

    def _load(self, records_path: str):
        records = load_roi_records(records_path)
        for r in records.get(self.camera_id, []):
            if r.get("type") == "line":
                self.lines.append({
                    "id": r["id"],
                    "label": r["label"],
                    "color": tuple(r["color"]),
                    "points": [tuple(pt) for pt in r["points"]],
                })
            else:
                self.zones.append({
                    "id": r["id"],
                    "label": r["label"],
                    "color": tuple(r["color"]),
                    "polygon": np.array(r["points"], np.int32),
                })

    # ── 區域查詢 ───────────────────────────────────────────────────────────────

    def get_zone_labels(self, cx: int, cy: int) -> list[str]:
        return [
            z["label"] for z in self.zones
            if cv2.pointPolygonTest(z["polygon"], (float(cx), float(cy)), False) >= 0
        ]

    def is_in_any_zone(self, cx: int, cy: int) -> bool:
        """無 zone 設定時視為全幀皆在範圍（無圍籬模式）。"""
        if not self.zones:
            return True
        return bool(self.get_zone_labels(cx, cy))

    # ── 跨線偵測 ───────────────────────────────────────────────────────────────

    def check_line_crossing(self, obj_id: int, cx: int, cy: int) -> list[str]:
        """回傳此幀被跨越的 line label 列表。"""
        crossed = []
        for line in self.lines:
            p1, p2 = line["points"][0], line["points"][1]
            side = self._side(cx, cy, p1, p2)
            key = (obj_id, line["id"])
            prev = self._line_states.get(key)
            if prev is not None and prev != 0 and side != 0 and prev != side:
                crossed.append(line["label"])
            self._line_states[key] = side
        return crossed

    def _side(self, px, py, a, b) -> int:
        val = (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])
        return 1 if val > 0 else (-1 if val < 0 else 0)

    # ── 繪製 ───────────────────────────────────────────────────────────────────

    def draw(self, frame: np.ndarray):
        for zone in self.zones:
            poly, color = zone["polygon"], zone["color"]
            overlay = frame.copy()
            cv2.fillPoly(overlay, [poly], color)
            result = cv2.addWeighted(overlay, 0.20, frame, 0.80, 0)
            np.copyto(frame, result)
            cv2.polylines(frame, [poly], True, color, 3)
            cv2.putText(frame, zone["label"], tuple(poly[0]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        for line in self.lines:
            p1, p2 = line["points"][0], line["points"][1]
            color = line["color"]
            cv2.line(frame, p1, p2, color, 3)
            mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2 - 10)
            cv2.putText(frame, line["label"], mid,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
