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

def get_edge_voice(speaker_name: str) -> str:
    """Lấy giọng edge-tts theo speaker."""
    gender = detect_speaker_gender(speaker_name)
    return EDGE_VOICES.get(gender, EDGE_VOICES["default"])

def get_google_voice(speaker_name: str) -> str:
    """Lấy giọng Google Cloud TTS theo speaker."""
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


# ============================================================
# TTS Providers
# ============================================================

class EdgeTTSProvider:
    """edge-tts: miễn phí, Microsoft Neural voices."""
    name = "edge"

    def synthesize(self, text: str, speaker: str, output_path: str):
        voice = get_edge_voice(speaker)
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

    def synthesize(self, text: str, speaker: str, output_path: str):
        from google.cloud import texttospeech
        voice_name = get_google_voice(speaker)
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

def generate_tts_for_subtitles(subtitles: list, output_dir: str = "output/tts",
                                provider: str = "edge") -> list:
    """
    Tạo file MP3 cho mỗi subtitle segment.

    Args:
        subtitles: list các segment có 'translation', 'speaker', 'start', 'end'
        output_dir: thư mục output
        provider: 'edge' (mặc định, miễn phí) hoặc 'google' (cao cấp)

    Returns:
        list segment với thêm key 'audio_path'
    """
    # Chọn provider
    if provider == "google":
        tts = GoogleTTSProvider()
    else:
        tts = EdgeTTSProvider()

    logger.info(f"Generating TTS for {len(subtitles)} segments using [{tts.name}] provider...")
    os.makedirs(output_dir, exist_ok=True)

    updated_subtitles = []
    google_failures = 0

    for idx, sub in enumerate(subtitles):
        text = sub.get("translation", "")
        speaker = sub.get("speaker", "default")

        text = text.replace("[", "").replace("]", "").strip()
        if not text:
            continue

        file_path = os.path.join(output_dir, f"tts_{idx:04d}.mp3")

        try:
            tts.synthesize(text, speaker, file_path)

            # Điều chỉnh tốc độ để khớp duration segment gốc
            segment_duration = sub["end"] - sub["start"]
            adjusted_path = os.path.join(output_dir, f"tts_{idx:04d}_adjusted.mp3")
            final_path = adjust_tts_speed(file_path, adjusted_path, segment_duration)

            # Dọn file gốc nếu đã tạo adjusted (tránh lãng phí ổ cứng)
            if final_path != file_path:
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Không quan trọng nếu xóa thất bại

            sub_copy = dict(sub)
            sub_copy["audio_path"] = os.path.abspath(final_path)
            updated_subtitles.append(sub_copy)
        except Exception as e:
            logger.error(f"[{tts.name}] Failed segment {idx}: {e}")
            if provider == "google":
                google_failures += 1

    # Nếu Google TTS thất bại toàn bộ → tự động fallback edge-tts
    if provider == "google" and google_failures > 0 and len(updated_subtitles) == 0:
        logger.error(
            f"Google Cloud TTS failed all {google_failures} segments! "
            f"Check: Cloud Text-to-Speech API enabled? Service account has permission? "
            f"Falling back to edge-tts..."
        )
        return generate_tts_for_subtitles(subtitles, output_dir, provider="edge")
    elif provider == "google" and google_failures > 0:
        logger.warning(
            f"Google Cloud TTS: {google_failures}/{len(subtitles)} segments failed."
        )

    return updated_subtitles
