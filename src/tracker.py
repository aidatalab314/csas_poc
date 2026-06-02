import time
from collections import OrderedDict
import numpy as np


class CentroidTracker:
    """
    質心追蹤器：跨幀指派物件 ID，記錄出現時間供 dwell time 計算。
    距離超過 max_match_px 的偵測結果視為新物件。
    """

    def __init__(self, max_disappeared: int = 30, max_match_px: int = 150):
        self.next_id = 0
        self.objects: OrderedDict[int, dict] = OrderedDict()
        self.disappeared: OrderedDict[int, int] = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_match_px = max_match_px

    def _register(self, cx: int, cy: int, det: dict) -> int:
        obj_id = self.next_id
        self.objects[obj_id] = {
            "cx": cx, "cy": cy,
            "appeared_at": time.time(),
            "det": det,
        }
        self.disappeared[obj_id] = 0
        self.next_id += 1
        return obj_id

    def _deregister(self, obj_id: int):
        del self.objects[obj_id]
        del self.disappeared[obj_id]

    def update(self, detections: list[dict]) -> dict[int, dict]:
        """
        以偵測結果更新追蹤狀態。
        回傳 {obj_id: {cx, cy, appeared_at, dwell_seconds, det}}
        """
        if not detections:
            for obj_id in list(self.disappeared):
                self.disappeared[obj_id] += 1
                if self.disappeared[obj_id] > self.max_disappeared:
                    self._deregister(obj_id)
            return self._snapshot()

        centroids = np.array([(d["cx"], d["cy"]) for d in detections], dtype=float)

        if not self.objects:
            for i, (cx, cy) in enumerate(centroids):
                self._register(int(cx), int(cy), detections[i])
            return self._snapshot()

        obj_ids = list(self.objects)
        obj_centroids = np.array([(o["cx"], o["cy"]) for o in self.objects.values()], dtype=float)

        # 距離矩陣 [num_objects × num_detections]
        D = np.linalg.norm(obj_centroids[:, None] - centroids[None, :], axis=2)

        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        used_rows, used_cols = set(), set()
        for row, col in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue
            if D[row, col] > self.max_match_px:
                continue
            obj_id = obj_ids[row]
            cx, cy = int(centroids[col][0]), int(centroids[col][1])
            self.objects[obj_id]["cx"] = cx
            self.objects[obj_id]["cy"] = cy
            self.objects[obj_id]["det"] = detections[col]
            self.disappeared[obj_id] = 0
            used_rows.add(row)
            used_cols.add(col)

        for row in set(range(len(obj_ids))) - used_rows:
            obj_id = obj_ids[row]
            self.disappeared[obj_id] += 1
            if self.disappeared[obj_id] > self.max_disappeared:
                self._deregister(obj_id)

        for col in set(range(len(detections))) - used_cols:
            cx, cy = int(centroids[col][0]), int(centroids[col][1])
            self._register(cx, cy, detections[col])

        return self._snapshot()

    def _snapshot(self) -> dict[int, dict]:
        now = time.time()
        return {
            obj_id: {**obj, "dwell_seconds": now - obj["appeared_at"]}
            for obj_id, obj in self.objects.items()
        }
