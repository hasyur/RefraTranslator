from game_screen_translator.ocr.paddle import PaddleOcrEngine
from game_screen_translator.ocr.roi import recognize_ocr_roi, recognize_ocr_rois
from game_screen_translator.ocr.types import OcrText

__all__ = [
    "OcrText",
    "PaddleOcrEngine",
    "recognize_ocr_roi",
    "recognize_ocr_rois",
]
