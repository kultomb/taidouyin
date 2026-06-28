import os
import asyncio
import subprocess
import edge_tts
import logging
from pathlib import Path

logger = logging.getLogger("douyin_translator")

# ============================================================
# Voice mappings
# ============================================================

# edge-tts voices (free, Microsoft neural)
EDGE_VOICES = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
    "default": "vi-VN-HoaiMyNeural",
}

# Google Cloud TTS voices (premium, Vertex AI Neural2)
# Docs: https://cloud.google.com/text-to-speech/docs/voices
GOOGLE_VOICES = {
    "female": "vi-VN-Neural2-A",
    "male": "vi-VN-Neural2-D",
    "default": "vi-VN-Neural2-A",
}

def detect_speaker_gender(speaker_name: str) -> str:
    """Phân tích tên speaker để xác định giới tính: 'male' hoặc 'female'."""
    if not speaker_name:
        return "female"
    clean = speaker_name.lower().strip()
    if "b" in clean or "2" in clean or "nam" in clean:
        return "male"
    return "female"

def get_edge_voice(speaker_name: str, voice_map: dict = None) -> str:
    """Lấy giọng edge-tts theo speaker."""
    if voice_map and speaker_name in voice_map:
        return voice_map[speaker_name]
    gender = detect_speaker_gender(speaker_name)
    return EDGE_VOICES.get(gender, EDGE_VOICES["default"])

def get_google_voice(speaker_name: str, voice_map: dict = None) -> str:
    """Lấy giọng Google Cloud TTS theo speaker."""
    if voice_map and speaker_name in voice_map:
        return voice_map[speaker_name]
    gender = detect_speaker_gender(speaker_name)
    return GOOGLE_VOICES.get(gender, GOOGLE_VOICES["default"])


# ============================================================
# Audio utilities (dùng chung)
# ============================================================

def get_audio_duration(file_path: str) -> float:
    """Đo duration thật của file audio bằng ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Không thể đo duration của {file_path}: {e}")
        return 0.0

def adjust_tts_speed(input_path: str, output_path: str, target_duration: float) -> str:
    """
    Điều chỉnh tốc độ file TTS bằng atempo để khớp với target_duration.
    Nếu chênh lệch < 10% thì không cần chỉnh.
    """
    actual_duration = get_audio_duration(input_path)
    if actual_duration <= 0 or target_duration <= 0:
        return input_path

    ratio = actual_duration / target_duration
    if 0.9 <= ratio <= 1.1:
        return input_path

    atempo = ratio
    logger.info(f"Adjusting TTS speed: {actual_duration:.2f}s -> {target_duration:.2f}s (atempo={atempo:.3f})")

    try:
        if atempo < 0.5:
            atempo_filter = f"atempo={atempo * 2:.4f},atempo=0.5"
        elif atempo > 2.0:
            atempo_filter = f"atempo={atempo / 2:.4f},atempo=2.0"
        else:
            atempo_filter = f"atempo={atempo:.4f}"

        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-filter:a", atempo_filter, "-q:a", "2", output_path
        ], capture_output=True, check=True, timeout=30)
        return output_path
    except Exception as e:
        logger.warning(f"Failed to adjust TTS speed: {e}, using original")
        return input_path


def trim_silence(input_path: str, output_path: str) -> bool:
    """Cắt khoảng lặng ở ĐẦU VÀ CUỐI file MP3 bằng FFmpeg silenceremove.
    stop_periods=-1: tự động lặp cho đến khi hết khoảng lặng ở cuối.
    stop_threshold=-45dB: ngưỡng cao hơn để cắt đuôi lặng triệt để hơn.
    stop_duration=0.15: cắt khi im lặng > 150ms (tránh cắt ngắt nghỉ tự nhiên ngắn)."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB:stop_periods=-1:stop_threshold=-45dB:stop_duration=0.15",
        "-c:a", "libmp3lame", "-q:a", "2",
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=15)
        return True
    except Exception as e:
        logger.warning(f"Failed to trim silence for {input_path}: {e}")
        return False


# ============================================================
# TTS Providers
# ============================================================

class EdgeTTSProvider:
    """edge-tts: miễn phí, Microsoft Neural voices."""
    name = "edge"

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None):
        voice = get_edge_voice(speaker, voice_map)
        logger.info(f"[edge-tts] '{text[:30]}...' -> {voice}")
        async def _run():
            await edge_tts.Communicate(text, voice).save(output_path)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech: cao cấp, Neural2 voices."""
    name = "google"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import texttospeech
            self._client = texttospeech.TextToSpeechClient()
        return self._client

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None):
        from google.cloud import texttospeech
        voice_name = get_google_voice(speaker, voice_map)
        logger.info(f"[Google TTS] '{text[:30]}...' -> {voice_name}")

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="vi-VN",
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0,
        )

        response = self.client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )

        with open(output_path, "wb") as f:
            f.write(response.audio_content)


# ============================================================
# Main TTS generator
# ============================================================

# Số segment TTS chạy song song (edge-tts: 10, Google TTS: 5 để tránh rate limit)
TTS_CONCURRENCY = {"edge": 10, "google": 5}

async def _synthesize_edge_async(text: str, speaker: str, output_path: str, voice_map: dict = None):
    """edge-tts async wrapper."""
    voice = get_edge_voice(speaker, voice_map)
    await edge_tts.Communicate(text, voice).save(output_path)

def _synthesize_google_sync(tts: GoogleTTSProvider, text: str, speaker: str, output_path: str, voice_map: dict = None):
    """Google TTS sync wrapper (dùng trong thread pool)."""
    tts.synthesize(text, speaker, output_path, voice_map)

async def _generate_tts_concurrent(subtitles: list, output_dir: str, provider: str, voice_map: dict = None) -> tuple:
    """
    Tạo TTS song song cho tất cả segment.
    Returns: (updated_subtitles, failure_count)
    """
    import concurrent.futures
    
    concurrency = TTS_CONCURRENCY.get(provider, 5)
    semaphore = asyncio.Semaphore(concurrency)
    updated = [None] * len(subtitles)
    failures = 0
    lock = asyncio.Lock()
    
    if provider == "google":
        tts = GoogleTTSProvider()
    else:
        tts = None  # edge-tts doesn't need persistent client
    
    async def process_one(idx: int, sub: dict):
        nonlocal failures
        text = sub.get("translation", "")
        speaker = sub.get("speaker", "default")
        text = text.replace("[", "").replace("]", "").strip()
        if not text:
            return
        
        file_path = os.path.join(output_dir, f"tts_{idx:04d}.mp3")
        
        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                if provider == "google":
                    await loop.run_in_executor(
                        None, _synthesize_google_sync, tts, text, speaker, file_path, voice_map
                    )
                else:
                    await _synthesize_edge_async(text, speaker, file_path, voice_map)
                
                # Cắt bỏ khoảng lặng đầu/cuối của file âm thanh vừa tạo
                trimmed_file_path = file_path + ".trimmed.mp3"
                success = await loop.run_in_executor(
                    None, trim_silence, file_path, trimmed_file_path
                )
                if success and os.path.exists(trimmed_file_path):
                    os.replace(trimmed_file_path, file_path)
                
                actual_duration = await loop.run_in_executor(None, get_audio_duration, file_path)
                
                async with lock:
                    sub_copy = dict(sub)
                    sub_copy["audio_path"] = os.path.abspath(file_path)
                    sub_copy["tts_duration"] = actual_duration
                    updated[idx] = sub_copy
            except Exception as e:
                logger.error(f"[{provider}] Failed segment {idx}: {e}")
                async with lock:
                    failures += 1
    
    tasks = [process_one(i, sub) for i, sub in enumerate(subtitles)]
    await asyncio.gather(*tasks)
    
    filtered_updated = [item for item in updated if item is not None]
    return filtered_updated, failures


def generate_tts_for_subtitles(subtitles: list, output_dir: str = "output/tts",
                                provider: str = "edge", voice_map: dict = None) -> list:
    """
    Tạo file MP3 song song cho tất cả subtitle segment.

    Args:
        subtitles: list các segment có 'translation', 'speaker', 'start', 'end'
        output_dir: thư mục output
        provider: 'edge' (mặc định, miễn phí) hoặc 'google' (cao cấp)
        voice_map: dict ánh xạ Speaker -> giọng đọc cụ thể (tùy chọn)

    Returns:
        list segment với thêm key 'audio_path', 'tts_duration'
    """
    provider_label = "Google Cloud TTS" if provider == "google" else "edge-tts"
    concurrency = TTS_CONCURRENCY.get(provider, 5)
    logger.info(f"Generating TTS for {len(subtitles)} segments [{provider_label}] ({concurrency} concurrent)...")
    os.makedirs(output_dir, exist_ok=True)
    
    # Chạy async event loop
    loop = asyncio.new_event_loop()
    try:
        updated_subtitles, google_failures = loop.run_until_complete(
            _generate_tts_concurrent(subtitles, output_dir, provider, voice_map)
        )
    finally:
        loop.close()
    
    logger.info(f"TTS done: {len(updated_subtitles)}/{len(subtitles)} segments, {google_failures} failed")
    
    # Nếu Google TTS thất bại toàn bộ → tự động fallback edge-tts
    if provider == "google" and google_failures > 0 and len(updated_subtitles) == 0:
        logger.error(
            f"Google Cloud TTS failed all {google_failures} segments! "
            f"Falling back to edge-tts..."
        )
        return generate_tts_for_subtitles(subtitles, output_dir, provider="edge", voice_map=voice_map)
    elif provider == "google" and google_failures > 0:
        logger.warning(f"Google Cloud TTS: {google_failures}/{len(subtitles)} segments failed.")
    
    return updated_subtitles
