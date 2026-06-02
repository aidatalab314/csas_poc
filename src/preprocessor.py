"""
影像前處理模組（移植自 KMetro_cv FallDetector / PoseDetector）

支援技術：
  1. Gamma 校正   — LUT 查表法，< 1 提亮暗部，> 1 壓暗高光，1.0 = 關閉
  2. CLAHE        — 自適應直方圖均衡化（LAB L 通道），保留色彩不偏移
  3. imgsz        — YOLO 推論解析度（由 Detector 使用，此處不處理）

設定範例（cameras.yaml）：
  preprocess:
    gamma: 0.7          # 1.0 = 關閉；< 1 提亮（建議 0.5~0.8）
    clahe: true         # CLAHE 對比增強
    clahe_clip: 3.0     # clipLimit，越高對比增強越強（建議 2.0~4.0）
    clahe_grid: [8, 8]  # tileGridSize
"""

import cv2
import numpy as np


class Preprocessor:
    def __init__(self,
                 gamma: float = 1.0,
                 clahe: bool = False,
                 clahe_clip: float = 3.0,
                 clahe_grid: tuple = (8, 8)):
        self._gamma_lut = self._build_gamma_lut(gamma) if gamma != 1.0 else None
        self._clahe = (cv2.createCLAHE(clipLimit=clahe_clip,
                                        tileGridSize=tuple(clahe_grid))
                       if clahe else None)

    @staticmethod
    def _build_gamma_lut(gamma: float) -> np.ndarray:
        return np.array(
            [(i / 255.0) ** gamma * 255 for i in range(256)],
            dtype=np.uint8,
        )

    def apply(self, frame: np.ndarray) -> np.ndarray:
        # 1. Gamma 校正（LUT 查表，低成本）
        if self._gamma_lut is not None:
            frame = cv2.LUT(frame, self._gamma_lut)

        # 2. CLAHE（LAB L 通道，不影響色彩）
        if self._clahe is not None:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = self._clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)

        return frame

    @classmethod
    def from_config(cls, cfg: dict) -> "Preprocessor":
        """從 cameras.yaml preprocess 區塊建立實例。"""
        return cls(
            gamma=cfg.get("gamma", 1.0),
            clahe=cfg.get("clahe", False),
            clahe_clip=cfg.get("clahe_clip", 3.0),
            clahe_grid=cfg.get("clahe_grid", [8, 8]),
        )

    @property
    def is_noop(self) -> bool:
        """兩項處理都關閉時為 True（可跳過 apply 節省 CPU）。"""
        return self._gamma_lut is None and self._clahe is None
