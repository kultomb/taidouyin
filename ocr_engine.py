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
MIN_SEG_DUR   = 0.20   # độ dài tối thiểu của 1 segment (giây)
MIN_TEXT_LEN  = 3      # độ dài text tối thiểu (bỏ qua logo/nhiễu 1-2 ký tự)
OCR_CONF_MIN  = 0.45   # confidence tối thiểu để giữ text
MAX_OCR_PER_SEC = 4.0  # giới hạn số lần OCR mỗi giây (tránh quét logo/intro)

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


def _is_valid_chinese_text(text: str) -> bool:
    """Kiểm tra text có chứa ít nhất 2 ký tự CJK (Trung/Nhật/Hàn)."""
    cjk_count = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf')
    return cjk_count >= 2


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
        joined = "".join(texts)  # tiếng Trung không có khoảng trắng giữa từ

        # Filter: nếu không có ít nhất 2 ký tự CJK → bỏ qua (logo/nhiễu)
        if joined and not _is_valid_chinese_text(joined):
            return ""
        return joined
    except Exception as exc:
        logger.warning(f"RapidOCR lỗi: {exc}")
        return ""


def _normalize_for_comparison(text: str) -> str:
    """Loại bỏ khoảng trắng và dấu câu thông dụng tiếng Trung/Anh để so khớp trùng lặp."""
    import string
    puncts = string.punctuation + "，。！？；：（）“”‘’~…—_ "
    return "".join(ch for ch in text.lower() if ch not in puncts)


def _is_similar(s1: str, s2: str) -> bool:
    """Kiểm tra độ tương đồng giữa 2 chuỗi để gộp phụ đề OCR bị nhiễu/lặp."""
    import difflib
    norm1 = _normalize_for_comparison(s1)
    norm2 = _normalize_for_comparison(s2)
    
    if norm1 == norm2:
        return True
        
    if not norm1 or not norm2:
        return False
        
    # 1. Đo độ tương đồng ratio
    ratio = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    if ratio >= 0.7:
        return True
        
    # 2. Kiểm tra xem một chuỗi có chứa chuỗi kia hay không (ví dụ: "看清楚了" và "看清楚了LG")
    if (norm1 in norm2 or norm2 in norm1) and min(len(norm1), len(norm2)) >= 2:
        return True
        
    # 3. Kiểm tra tiền tố / hậu tố chung chiếm đa số độ dài
    min_len = min(len(norm1), len(norm2))
    if min_len >= 3:
        # Tiền tố chung
        pref_len = 0
        while pref_len < min_len and norm1[pref_len] == norm2[pref_len]:
            pref_len += 1
        # Hậu tố chung
        suff_len = 0
        while suff_len < min_len and norm1[len(norm1) - 1 - suff_len] == norm2[len(norm2) - 1 - suff_len]:
            suff_len += 1
            
        if (pref_len / min_len) >= 0.6 or (suff_len / min_len) >= 0.6:
            return True
            
    return False


def _choose_better_text(t1: str, t2: str) -> str:
    """Chọn chuỗi có tỷ lệ ký tự CJK (tiếng Trung) cao hơn để loại bỏ rác OCR Latin/số."""
    if not t1:
        return t2
    if not t2:
        return t1
        
    def score(t):
        cjk = sum(1 for ch in t if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf')
        return cjk / len(t)
        
    return t1 if score(t1) >= score(t2) else t2


def extract_subtitle_segments(
    video_path: str,
    y_start_ratio: float,
    y_end_ratio: float,
    x_start_ratio: float = 0.0,
    x_end_ratio: float = 1.0,
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
        x_start_ratio:    viền trái vùng phụ đề (0.0–1.0 chiều rộng)
        x_end_ratio:      viền phải vùng phụ đề (0.0–1.0 chiều rộng)
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
    x0 = max(0,     int(vid_w * x_start_ratio))
    x1 = min(vid_w, int(vid_w * x_end_ratio))

    _log(
        f"Video: {vid_w}×{vid_h} @ {native_fps:.1f}fps, {duration:.1f}s | "
        f"Vùng quét: x=[{x0}–{x1}px] y=[{y0}–{y1}px] | "
        f"Sample mỗi {frame_step} frame (~{sample_fps}fps)"
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
    last_ocr_ts = -99.0  # giới hạn tần suất OCR theo thời gian

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            ts     = frame_idx / native_fps
            region = frame[y0:y1, x0:x1]
            gray   = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            clean  = cv2.morphologyEx(gray, cv2.MORPH_OPEN, morph_k)

            frame_count += 1

            if prev_clean is None:
                do_ocr = True
            else:
                diff   = cv2.absdiff(clean, prev_clean)
                do_ocr = diff.mean() > change_threshold

            # Giới hạn tần suất OCR: không OCR quá MAX_OCR_PER_SEC lần/giây
            if do_ocr and (ts - last_ocr_ts) < (1.0 / MAX_OCR_PER_SEC):
                do_ocr = False

            if do_ocr:
                ocr_count += 1
                last_ocr_ts = ts
                new_text = _ocr_region(region).strip()

                # Filter rác: text quá ngắn (logo/intro 1-2 ký tự lẻ)
                if new_text and len(new_text) < MIN_TEXT_LEN:
                    new_text = ""

                # Check similarity: nếu new_text tương đồng với cur_text, ta coi như cùng một phụ đề
                is_same_sub = False
                if cur_text and new_text and _is_similar(cur_text, new_text):
                    is_same_sub = True
                    # Cập nhật sang chuỗi tốt/sạch hơn
                    cur_text = _choose_better_text(cur_text, new_text)

                if new_text != cur_text and not is_same_sub:
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

    # Gộp các đoạn phụ đề trùng lặp liên tiếp có khoảng cách nhỏ (<= 1.5s)
    merged_segments = []
    if segments:
        _log("Đang gộp các đoạn phụ đề OCR trùng lặp liên tiếp...")
        prev = segments[0]
        for cur in segments[1:]:
            gap = cur["start"] - prev["end"]
            norm_cur = _normalize_for_comparison(cur["text"])
            norm_prev = _normalize_for_comparison(prev["text"])
            if norm_cur == norm_prev and gap <= 1.5:
                prev["end"] = max(prev["end"], cur["end"])
                _log(f"  Gộp đoạn trùng lặp: '{prev['text'][:30]}' -> {prev['start']:.2f}s–{prev['end']:.2f}s")
            else:
                merged_segments.append(prev)
                prev = cur
        merged_segments.append(prev)
        segments = merged_segments

    _log(
        f"✅ Quét xong: {frame_count} frames sampled | "
        f"{ocr_count} lần OCR | {len(segments)} đoạn phụ đề tìm được (sau khi gộp trùng lặp)."
    )
    return segments
