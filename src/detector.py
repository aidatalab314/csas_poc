import numpy as np
from ultralytics import YOLO
from src.preprocessor import Preprocessor


class Detector:
    """
    YOLO-based 偵測器，支援任意 YOLO 模型與目標類別篩選。
    推論前可選擇性套用 Preprocessor（Gamma 校正 + CLAHE）。
    回傳統一格式：{class_id, label, conf, bbox:(x1,y1,x2,y2), cx, cy}
    """

    def __init__(self, model_path: str, conf: float = 0.4,
                 device: str = "cpu", target_classes: list = None,
                 imgsz: int = 640, preprocessor: Preprocessor = None):
        self.model = YOLO(model_path)
        self.conf = conf
        self.device = device
        self.target_classes = target_classes  # None = 偵測全部類別
        self.imgsz = imgsz
        self.preprocessor = preprocessor      # None = 不前處理

    def detect(self, frame: np.ndarray) -> list[dict]:
        if self.preprocessor and not self.preprocessor.is_noop:
            frame = self.preprocessor.apply(frame)

        results = self.model(
            frame, conf=self.conf, device=self.device,
            imgsz=self.imgsz, verbose=False,
        )
        detections = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls = int(box.cls[0])
                if self.target_classes and cls not in self.target_classes:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "class_id": cls,
                    "label": r.names[cls],
                    "conf": float(box.conf[0]),
                    "bbox": (x1, y1, x2, y2),
                    "cx": (x1 + x2) // 2,
                    "cy": (y1 + y2) // 2,
                })
        return detections
