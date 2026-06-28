"""
Hybrid OCR Engine – trích xuất phụ đề cứng từ video.

Pipeline:
    Video
      ↓ OpenCV: sample 10fps
      ↓ OpenCV absdiff: phát hiện thay đổi vùng phụ đề
      ↓ RapidOCR (PaddleOCR ONNX): chỉ OCR khi có thay đổi
      ↓ State machine: ghép {start, end, text}
      ↓ [{start, end, text}, ...]

RapidOCR = model PaddleOCR chạy qua ONNX runtime.
- Không cần paddlepaddle, không conflict protobuf với Google SDK.
- Hỗ trợ chữ Trung giản thể tốt.
- Timestamp chính xác 100% (đo từ frame thật, không phụ thuộc AI).
"""

import cv2
import numpy as np
import logging
from typing import Callable, Optional

logger = logging.getLogger("douyin_translator")

# ─── Hằng số ─────────────────────────────────────────────────────────────────
SAMPLE_FPS    = 10     # frame/giây sample (0.1s precision)
CHANGE_THRESH = 8.0    # ngưỡng mean pixel diff để trigger re-OCR
MIN_SEG_DUR   = 0.25   # độ dài tối thiểu của 1 segment (giây)
OCR_CONF_MIN  = 0.45   # confidence tối thiểu để giữ text

# ─── RapidOCR singleton ───────────────────────────────────────────────────────
_rapid_ocr = None


def _get_ocr():
    """Lazy init RapidOCR (lần đầu tải ONNX model ~5s)."""
    global _rapid_ocr
    if _rapid_ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa
            logger.info("Khởi tạo RapidOCR engine...")
            _rapid_ocr = RapidOCR()
            logger.info("RapidOCR sẵn sàng.")
        except ImportError as exc:
            raise ImportError(
                "RapidOCR chưa cài. Chạy: pip install rapidocr-onnxruntime"
            ) from exc
    return _rapid_ocr


def _ocr_region(region_bgr: np.ndarray) -> str:
    """
    OCR một vùng ảnh BGR. Trả về text ghép lại, empty nếu không nhận ra.
    Tự động scale lên nếu vùng quá nhỏ (< 50px chiều cao).
    """
    if region_bgr is None or region_bgr.size == 0:
        return ""

    h, w = region_bgr.shape[:2]
    if h < 50:
        scale = max(2.0, 50.0 / h)
        region_bgr = cv2.resize(
            region_bgr,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    try:
        ocr = _get_ocr()
        result, _ = ocr(region_bgr)
        if not result:
            return ""
        texts = []
        for item in result:
            # item format: [box, text, score]
            if len(item) >= 3:
                text, score = item[1], item[2]
                if score >= OCR_CONF_MIN and text and text.strip():
                    texts.append(text.strip())
        return "".join(texts)  # tiếng Trung không có khoảng trắng giữa từ
    except Exception as exc:
        logger.warning(f"RapidOCR lỗi: {exc}")
        return ""


def extract_subtitle_segments(
    video_path: str,
    y_start_ratio: float,
    y_end_ratio: float,
    sample_fps: float = SAMPLE_FPS,
    change_threshold: float = CHANGE_THRESH,
    log_func: Optional[Callable] = None,
) -> list:
    """
    Trích xuất phụ đề cứng từ video bằng OpenCV + RapidOCR.

    Args:
        video_path:       đường dẫn video
        y_start_ratio:    viền trên vùng phụ đề (0.0–1.0 chiều cao)
        y_end_ratio:      viền dưới vùng phụ đề (0.0–1.0 chiều cao)
        sample_fps:       số frame/giây sample
        change_threshold: mean pixel diff để trigger re-OCR
        log_func:         callback log

    Returns:
        list of {'start': float, 'end': float, 'text': str}
    """
    _log = log_func or logger.info

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Không thể mở video: {video_path}")

    native_fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_h        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    vid_w        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    duration     = total_frames / native_fps if native_fps > 0 else 0.0

    frame_step = max(1, int(round(native_fps / sample_fps)))
    y0 = max(0,     int(vid_h * y_start_ratio))
    y1 = min(vid_h, int(vid_h * y_end_ratio))

    _log(
        f"Video: {vid_w}×{vid_h} @ {native_fps:.1f}fps, {duration:.1f}s | "
        f"Vùng phụ đề: y=[{y0}–{y1}px] | Sample mỗi {frame_step} frame (~{sample_fps}fps)"
    )
    _log("Khởi động RapidOCR (PaddleOCR ONNX)...")
    _get_ocr()  # warm-up
    _log("Bắt đầu quét subtitle frame-by-frame...")

    morph_k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    segments    = []
    prev_clean  = None
    cur_text    = None
    cur_start   = None
    ocr_count   = 0
    frame_count = 0
    frame_idx   = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            ts     = frame_idx / native_fps
            region = frame[y0:y1, 0:vid_w]
            gray   = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            clean  = cv2.morphologyEx(gray, cv2.MORPH_OPEN, morph_k)

            frame_count += 1

            if prev_clean is None:
                do_ocr = True
            else:
                diff   = cv2.absdiff(clean, prev_clean)
                do_ocr = diff.mean() > change_threshold

            if do_ocr:
                ocr_count += 1
                new_text = _ocr_region(region).strip()

                if new_text != cur_text:
                    # Đóng segment cũ
                    if cur_text and cur_start is not None:
                        dur = ts - cur_start
                        if dur >= MIN_SEG_DUR:
                            segments.append({
                                "start": round(cur_start, 3),
                                "end":   round(ts, 3),
                                "text":  cur_text,
                            })
                            _log(f"  [{cur_start:.2f}s–{ts:.2f}s] '{cur_text[:50]}'")

                    cur_text  = new_text or None
                    cur_start = ts if new_text else None

            prev_clean = clean

        frame_idx += 1

    cap.release()

    # Đóng segment cuối
    if cur_text and cur_start is not None:
        seg_end = max(cur_start + MIN_SEG_DUR, duration)
        segments.append({
            "start": round(cur_start, 3),
            "end":   round(seg_end, 3),
            "text":  cur_text,
        })
        _log(f"  [{cur_start:.2f}s–{seg_end:.2f}s] '{cur_text[:50]}'")

    _log(
        f"✅ Quét xong: {frame_count} frames sampled | "
        f"{ocr_count} lần OCR | {len(segments)} đoạn phụ đề tìm được."
    )
    return segments
