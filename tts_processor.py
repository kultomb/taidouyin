import os
import asyncio
import subprocess
import edge_tts
import logging
from pathlib import Path

# Force set Google Cloud env vars (fallback if not set via run.bat)
if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    default_creds = "C:/Users/CMD/Downloads/123.json"
    if os.path.exists(default_creds):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = default_creds
if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
    os.environ["GOOGLE_CLOUD_PROJECT"] = "full-video-499000"
if not os.environ.get("GOOGLE_CLOUD_LOCATION"):
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"

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

# -------------------- Google Cloud TTS voices --------------------
# Docs: https://cloud.google.com/text-to-speech/docs/voices
# Chỉ giữ giọng đã test thành công trên Vertex AI (10/23 hoạt động)

# Gộp tất cả giọng đã xác nhận hoạt động
ALL_GOOGLE_VOICES = {
    "vi-VN-Neural2-A":   {"gender": "female", "label": "Neural2 A (Nữ HN)"},
    "vi-VN-Neural2-D":   {"gender": "male",   "label": "Neural2 D (Nam SG)"},
    "vi-VN-Standard-A":  {"gender": "female", "label": "Standard A (Nữ HN)"},
    "vi-VN-Standard-B":  {"gender": "male",   "label": "Standard B (Nam HN)"},
    "vi-VN-Standard-C":  {"gender": "female", "label": "Standard C (Nữ SG)"},
    "vi-VN-Standard-D":  {"gender": "male",   "label": "Standard D (Nam SG)"},
    "vi-VN-Wavenet-A":   {"gender": "female", "label": "Wavenet A (Nữ HN)"},
    "vi-VN-Wavenet-B":   {"gender": "male",   "label": "Wavenet B (Nam HN)"},
    "vi-VN-Wavenet-C":   {"gender": "female", "label": "Wavenet C (Nữ SG)"},
    "vi-VN-Wavenet-D":   {"gender": "male",   "label": "Wavenet D (Nam SG)"},
}

# Giọng mặc định phân vai (female / male)
_voice_list_female = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "female"]
_voice_list_male   = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "male"]

GOOGLE_VOICES = {
    "female": _voice_list_female[0] if _voice_list_female else "vi-VN-Neural2-A",
    "male":   _voice_list_male[0]   if _voice_list_male   else "vi-VN-Neural2-D",
    "default": _voice_list_female[0] if _voice_list_female else "vi-VN-Neural2-A",
}

# ============================================================
# Voice picker: phân phối giọng cho từng speaker
# ============================================================
_speaker_voice_index = {}  # cache index để cycle qua các giọng

def pick_voice_for_speaker(speaker_name: str, voice_map: dict = None, gender: str = None) -> str:
    """
    Chọn giọng Google TTS cho một speaker.
    - Nếu có voice_map, dùng giọng được chỉ định.
    - Nếu không, cycle qua danh sách giọng phù hợp giới tính để đa dạng hóa.
    """
    if voice_map and speaker_name in voice_map:
        return voice_map[speaker_name]

    g = gender or detect_speaker_gender(speaker_name)
    voices = _voice_list_female if g == "female" else _voice_list_male
    if not voices:
        return GOOGLE_VOICES.get(g, GOOGLE_VOICES["default"])

    # Cycle: mỗi speaker mới sẽ lấy giọng tiếp theo trong danh sách
    idx = _speaker_voice_index.get(speaker_name, len(_speaker_voice_index) % len(voices))
    _speaker_voice_index[speaker_name] = idx
    return voices[idx % len(voices)]

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
    """Lấy giọng Google Cloud TTS theo speaker (có phân phối đa dạng giọng)."""
    if voice_map and speaker_name in voice_map:
        return voice_map[speaker_name]
    return pick_voice_for_speaker(speaker_name, voice_map)


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
    return _apply_atempo(input_path, output_path, atempo, f"Adjust speed to fit {target_duration:.1f}s")

def speed_up_tts(input_path: str, speed: float = 1.2) -> str:
    """Tăng tốc file TTS lên speed X (mặc định 1.2x). Giữ nguyên pitch."""
    if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
        return input_path
    if speed <= 0.5 or speed >= 2.0:
        logger.warning(f"speed_up_tts: speed={speed} outside 0.5-2.0 range, skip")
        return input_path
    return _apply_atempo(input_path, input_path, speed, f"Spped up TTS {speed:.1f}x")

def _apply_atempo(input_path: str, output_path: str, atempo: float, log_msg: str) -> str:
    """Dùng FFmpeg atempo filter để thay đổi tốc độ audio (giữ nguyên pitch)."""
    if 0.98 <= atempo <= 1.02:
        return input_path
    if atempo < 0.5:
        atempo_filter = f"atempo={atempo * 2:.4f},atempo=0.5"
    elif atempo > 2.0:
        atempo_filter = f"atempo={atempo / 2:.4f},atempo=2.0"
    else:
        atempo_filter = f"atempo={atempo:.4f}"
    logger.info(f"{log_msg} | filter={atempo_filter}")
    try:
        subprocess.run(["ffmpeg", "-y", "-i", input_path,
            "-filter:a", atempo_filter, "-q:a", "2", output_path],
            capture_output=True, check=True, timeout=30)
        return output_path
    except Exception as e:
        logger.warning(f"Failed to apply atempo: {e}, using original")
        return input_path


def trim_silence(input_path: str, output_path: str) -> bool:
    """Cắt khoảng lặng ở ĐẦU VÀ CUỐI file audio bằng FFmpeg silenceremove.
    Hỗ trợ cả MP3, WAV, PCM từ Gemini TTS.
    stop_periods=-1: tự động lặp cho đến khi hết khoảng lặng ở cuối.
    stop_threshold=-45dB: ngưỡng cao hơn để cắt đuôi lặng triệt để hơn.
    stop_duration=0.15: cắt khi im lặng > 150ms (tránh cắt ngắt nghỉ tự nhiên ngắn)."""
    # Luôn re-encode ra MP3 để đảm bảo định dạng đồng nhất
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB:stop_periods=-1:stop_threshold=-45dB:stop_duration=0.15",
        "-c:a", "libmp3lame", "-q:a", "2",
        "-ar", "44100",  # chuẩn hóa sample rate
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

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
        voice = voice_name if voice_name else get_edge_voice(speaker, voice_map)
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

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
        from google.cloud import texttospeech
        voice_name_actual = voice_name if voice_name else get_google_voice(speaker, voice_map)
        logger.info(f"[Google TTS] '{text[:30]}...' -> {voice_name_actual}")

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="vi-VN",
            name=voice_name_actual,
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
# Gemini TTS Provider (30 giọng, model: gemini-2.5-flash-preview-tts)
# ============================================================

GEMINI_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda",
    "Orus", "Aoede", "Callirrhoe", "Autonoe", "Enceladus",
    "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome",
    "Algenib", "Rasalgethi", "Laomedeia", "Achernar", "Alnilam",
    "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat"
]

# Phân loại giới tính chính xác dựa trên danh sách chính thức Google Gemini TTS
# Nguồn: https://cloud.google.com/text-to-speech/docs/voices
_GEMINI_FEMALE = {
    "Zephyr", "Achernar", "Aoede", "Autonoe", "Despina",
    "Callirrhoe", "Erinome", "Gacrux", "Kore", "Leda",
    "Laomedeia", "Pulcherrima", "Sulafat", "Vindemiatrix"
}
_GEMINI_MALE = {
    "Charon", "Enceladus", "Fenrir", "Puck", "Achird",
    "Algenib", "Algieba", "Alnilam", "Orus", "Iapetus",
    "Rasalgethi", "Schedar", "Sadachbia", "Sadaltager",
    "Umbriel", "Zubenelgenubi"
}

GEMINI_VOICE_GENDER = {}
for v in GEMINI_VOICES:
    if v in _GEMINI_FEMALE:
        GEMINI_VOICE_GENDER[v] = "female"
    elif v in _GEMINI_MALE:
        GEMINI_VOICE_GENDER[v] = "male"
    else:
        GEMINI_VOICE_GENDER[v] = "female"

_gemini_speaker_index = {}

def _gemini_voice_to_edge_fallback(voice_name: str) -> str:
    """
    Ánh xạ giọng Gemini → giọng Edge tương ứng theo giới tính.
    Dùng khi Gemini TTS lỗi, fallback về edge-tts nhưng vẫn giữ đúng giới tính.
    """
    if not voice_name:
        return EDGE_VOICES["default"]
    gender = GEMINI_VOICE_GENDER.get(voice_name, "female")
    return EDGE_VOICES.get(gender, EDGE_VOICES["default"])

def pick_gemini_voice(speaker_name: str, voice_map: dict = None, voice_name: str = None) -> str:
    """
    Chọn giọng Gemini TTS cho speaker.
    Nếu có voice_map hoặc voice_name thì dùng giọng chỉ định.
    Nếu không, cycle qua danh sách để đa dạng.
    """
    if voice_name:
        return voice_name
    if voice_map and speaker_name in voice_map:
        return voice_map[speaker_name]

    gender = detect_speaker_gender(speaker_name)
    suitable = [v for v in GEMINI_VOICES if GEMINI_VOICE_GENDER.get(v) == gender]
    if not suitable:
        suitable = GEMINI_VOICES

    idx = _gemini_speaker_index.get(speaker_name, len(_gemini_speaker_index) % len(suitable))
    _gemini_speaker_index[speaker_name] = idx
    return suitable[idx % len(suitable)]


class GeminiTTSProvider:
    """Gemini TTS: 30 giọng AI chất lượng cao, model gemini-2.5-flash-preview-tts.
    Client được tạo 1 lần và share qua các thread."""
    name = "gemini"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            import os
            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
            creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
            
            logger.info(f"[Gemini] Init client: project={project}, location={location}, creds={'set' if creds else 'MISSING'}")
            
            if not project:
                logger.warning("[Gemini] GOOGLE_CLOUD_PROJECT not set! Trying 'full-video-499000'")
                project = "full-video-499000"
            
            self._client = genai.Client(
                vertexai=True,
                project=project,
                location=location
            )
        return self._client

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
        from google.genai import types

        voice_name_actual = pick_gemini_voice(speaker, voice_map, voice_name)
        logger.info(f"[Gemini TTS] '{text[:30]}...' -> {voice_name_actual}")

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            temperature=0.1,  # Giữ giọng nhất quán, không sáng tạo ngẫu nhiên
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name_actual)
                )
            )
        )

        client = self._get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=[text],
            config=config
        )

        if not response or not response.candidates:
            raise Exception("Gemini TTS returned an empty response (no candidates).")

        content = response.candidates[0].content
        if not content or not content.parts:
            raise Exception("Gemini TTS response candidate has no content or parts.")

        audio_found = False
        for part in content.parts:
            if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.lower().startswith("audio/"):
                mime = part.inline_data.mime_type.lower()
                if "pcm" in mime or "l16" in mime:
                    rate = 24000
                    if "rate=" in mime:
                        try:
                            rate = int(mime.split("rate=")[-1].split(";")[0].split(",")[0].strip())
                        except Exception:
                            pass
                    import tempfile
                    fd, tmp_path = tempfile.mkstemp(suffix=".pcm")
                    try:
                        with os.fdopen(fd, "wb") as tmp_f:
                            tmp_f.write(part.inline_data.data)
                        cmd = [
                            "ffmpeg", "-y",
                            "-f", "s16le",
                            "-ar", str(rate),
                            "-ac", "1",
                            "-i", tmp_path,
                            "-c:a", "libmp3lame", "-q:a", "2",
                            output_path
                        ]
                        subprocess.run(cmd, capture_output=True, check=True)
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                else:
                    with open(output_path, "wb") as f:
                        f.write(part.inline_data.data)
                audio_found = True
                break

        if not audio_found or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Gemini TTS failed to generate a valid audio file.")



# ============================================================
# Main TTS generator
# ============================================================

# Số segment TTS chạy song song (edge-tts: 10, Google TTS: 5, Gemini: 1 để tránh rate limit)
TTS_CONCURRENCY = {"edge": 10, "google": 5, "gemini": 1}

async def _synthesize_edge_async(text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
    """edge-tts async wrapper."""
    voice = voice_name if voice_name else get_edge_voice(speaker, voice_map)
    await edge_tts.Communicate(text, voice).save(output_path)

def _synthesize_google_sync(tts: GoogleTTSProvider, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
    """Google TTS sync wrapper (dùng trong thread pool)."""
    tts.synthesize(text, speaker, output_path, voice_map, voice_name)

def _synthesize_gemini_sync(tts: GeminiTTSProvider, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None):
    """Gemini TTS sync wrapper với retry mạnh - KHÔNG đổi giọng, KHÔNG bỏ cuộc dễ."""
    import time as _time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            tts.synthesize(text, speaker, output_path, voice_map, voice_name)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return
            raise Exception("Output file empty")
        except Exception as e:
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 5  # 5s, 10s, 15s, 20s
                logger.warning(f"[Gemini] Retry {attempt+1}/{max_retries} after {delay}s for speaker='{speaker}': {e}")
                _time.sleep(delay)
            else:
                logger.error(f"[Gemini] FAILED after {max_retries} retries for speaker='{speaker}': {e}")
                raise

async def _generate_tts_batch_gemini(subtitles: list, output_dir: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.2) -> tuple:
    """
    Gemini TTS: Group by speaker → merge text → 1 API call/speaker → split ffmpeg.
    Giữ giọng nhất quán trong cùng 1 speaker.
    Returns: (updated_subtitles, failure_count)
    """
    import time as _time
    
    tts = GeminiTTSProvider()
    updated = [None] * len(subtitles)
    failures = 0

    # 1. Group segments by speakerName (nếu có voice_name đồng nhất thì gộp tất cả)
    groups = {}  # {speaker_name: [(idx, sub), ...]}
    for i, sub in enumerate(subtitles):
        text = sub.get("translation", "").replace("[", "").replace("]", "").strip()
        if not text:
            updated[i] = dict(sub, audio_path="", tts_duration=max(0.1, sub.get("end", 0) - sub.get("start", 0)))
            continue
        # Nếu có voice_name đồng nhất → tất cả chung 1 speaker
        speaker_key = "__all__" if voice_name else sub.get("speaker", "default")
        groups.setdefault(speaker_key, []).append((i, sub))

    if not groups:
        return [s for s in updated if s is not None], 0

    logger.info(f"[Gemini Batch] {len(subtitles)} segments → {len(groups)} speaker groups")

    # 2. For each speaker: merge text → synthesize 1 lần → split
    for speaker, group_items in groups.items():
        voice = pick_gemini_voice(speaker, voice_map, voice_name)
        logger.info(f"[Gemini Batch] Speaker '{speaker}' ({len(group_items)} segments) → voice={voice}")

        merged_path = os.path.join(output_dir, f"tts_merged_{speaker.replace(' ','_')}.mp3")
        
        try:
            offsets = tts.synthesize_batch(
                [sub for _, sub in group_items],
                voice_name_actual=voice,
                output_path=merged_path
            )
        except Exception as e:
            logger.error(f"[Gemini Batch] FAILED speaker '{speaker}': {e}")
            for idx, sub in group_items:
                updated[idx] = dict(sub, audio_path="", tts_duration=max(0.1, sub.get("end", 0) - sub.get("start", 0)))
            failures += len(group_items)
            continue

        # 3. Split merged audio → từng segment bằng ffmpeg dựa trên timestamp
        merged_duration = get_audio_duration(merged_path)
        if merged_duration <= 0:
            logger.error(f"[Gemini Batch] Merged audio duration=0 for speaker '{speaker}'")
            for idx, sub in group_items:
                updated[idx] = dict(sub, audio_path="", tts_duration=max(0.1, sub.get("end", 0) - sub.get("start", 0)))
            failures += len(group_items)
            continue

        # Tính tổng độ dài text để phân bổ thời gian
        total_text_len = sum(len(sub.get("translation", "").strip()) for _, sub in group_items)
        if total_text_len == 0:
            total_text_len = 1

        time_cursor = 0.0
        for _seq_index, (idx, sub) in enumerate(group_items):
            text = sub.get("translation", "").strip()
            speaker_label = sub.get("speaker", "default")
            text_len = len(text)
            segment_ratio = text_len / total_text_len if total_text_len > 0 else 0
            segment_duration = merged_duration * segment_ratio
            
            file_path = os.path.join(output_dir, f"tts_{idx:04d}.mp3")
            
            try:
                # Cắt từ merged audio: ffmpeg -ss {start} -t {duration} -i input -c copy output
                subprocess.run([
                    "ffmpeg", "-y",
                    "-ss", f"{time_cursor:.3f}",
                    "-t", f"{segment_duration:.3f}",
                    "-i", merged_path,
                    "-c:a", "libmp3lame", "-q:a", "2",
                    file_path
                ], capture_output=True, check=True, timeout=15)
                
                time_cursor += segment_duration

                # Trim silence
                trimmed = file_path + ".trimmed.mp3"
                if trim_silence(file_path, trimmed) and os.path.exists(trimmed):
                    os.replace(trimmed, file_path)

                # Speed up
                if tts_speed != 1.0:
                    speed_up_tts(file_path, tts_speed)

                actual_duration = get_audio_duration(file_path)
                updated[idx] = dict(sub, audio_path=os.path.abspath(file_path), tts_duration=actual_duration)
                logger.info(f"[Gemini Batch] ✓ seg {idx} '{text[:30]}...' ({actual_duration:.1f}s)")

            except Exception as e:
                logger.error(f"[Gemini Batch] FAILED split seg {idx}: {e}")
                # Fallback: thử Edge TTS cho segment này
                try:
                    logger.info(f"[Gemini Batch] Fallback Edge TTS for seg {idx}...")
                    await _synthesize_edge_async(text, speaker_label, file_path, None, None)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        if tts_speed != 1.0:
                            speed_up_tts(file_path, tts_speed)
                        actual_duration = get_audio_duration(file_path)
                        updated[idx] = dict(sub, audio_path=os.path.abspath(file_path), tts_duration=actual_duration)
                        logger.info(f"[Gemini Batch] ✓ seg {idx} (Edge fallback) '{text[:30]}...' ({actual_duration:.1f}s)")
                        continue
                except Exception as fe:
                    logger.error(f"[Gemini Batch] Edge fallback also FAILED seg {idx}: {fe}")
                updated[idx] = dict(sub, audio_path="", tts_duration=max(0.1, sub.get("end", 0) - sub.get("start", 0)))
                failures += 1

        # Xóa merged file sau khi split xong
        try:
            if os.path.exists(merged_path):
                os.remove(merged_path)
        except Exception:
            pass

    filtered = [s for s in updated if s is not None]
    return filtered, failures


async def _generate_tts_concurrent(subtitles: list, output_dir: str, provider: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.2) -> tuple:
    """
    Tạo TTS song song cho tất cả segment.
    - Gemini: dùng batch merge (group by speaker)
    - Edge/Google: dùng concurrent per-segment
    Returns: (updated_subtitles, failure_count)
    """
    # Gemini → batch mode
    if provider == "gemini":
        return await _generate_tts_batch_gemini(subtitles, output_dir, voice_map, voice_name, tts_speed)

    # Edge/Google → concurrent per-segment (giữ nguyên logic cũ)
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
            success_segment = False
            loop = asyncio.get_event_loop()
            try:
                if provider == "gemini":
                    await loop.run_in_executor(
                        None, _synthesize_gemini_sync, tts, text, speaker, file_path, voice_map, voice_name
                    )
                elif provider == "google":
                    await loop.run_in_executor(
                        None, _synthesize_google_sync, tts, text, speaker, file_path, voice_map, voice_name
                    )
                else:
                    await _synthesize_edge_async(text, speaker, file_path, voice_map, voice_name)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    success_segment = True
                else:
                    raise Exception("Output file was not generated or is empty.")
            except Exception as e:
                logger.error(f"[{provider}] FAILED segment {idx} (speaker='{speaker}', text='{text[:40]}...'): {e}")

            if success_segment:
                try:
                    # Cắt bỏ khoảng lặng đầu/cuối của file âm thanh vừa tạo
                    trimmed_file_path = file_path + ".trimmed.mp3"
                    success_trim = await loop.run_in_executor(
                        None, trim_silence, file_path, trimmed_file_path
                    )
                    if success_trim and os.path.exists(trimmed_file_path):
                        os.replace(trimmed_file_path, file_path)

                    # Tăng tốc giọng đọc theo tts_speed (mặc định 1.2x)
                    if provider in ("gemini", "google") and tts_speed != 1.0:
                        await loop.run_in_executor(None, speed_up_tts, file_path, tts_speed)
                    
                    actual_duration = await loop.run_in_executor(None, get_audio_duration, file_path)
                    
                    async with lock:
                        sub_copy = dict(sub)
                        sub_copy["audio_path"] = os.path.abspath(file_path)
                        sub_copy["tts_duration"] = actual_duration
                        updated[idx] = sub_copy
                except Exception as post_e:
                    logger.error(f"Failed processing audio for segment {idx}: {post_e}")
                    async with lock:
                        failures += 1
                        # Fallback: keep the segment in SRT even if post-processing failed
                        sub_copy = dict(sub)
                        sub_copy["audio_path"] = ""
                        sub_copy["tts_duration"] = max(0.1, sub.get("end", 0) - sub.get("start", 0))
                        updated[idx] = sub_copy
            else:
                async with lock:
                    failures += 1
                    # Fallback: keep the segment in SRT even if synthesis failed
                    sub_copy = dict(sub)
                    sub_copy["audio_path"] = ""
                    sub_copy["tts_duration"] = max(0.1, sub.get("end", 0) - sub.get("start", 0))
                    updated[idx] = sub_copy
    
    tasks = [process_one(i, sub) for i, sub in enumerate(subtitles)]
    await asyncio.gather(*tasks)
    
    filtered_updated = [item for item in updated if item is not None]
    return filtered_updated, failures


def generate_tts_for_subtitles(subtitles: list, output_dir: str = "output/tts",
                                provider: str = "edge", voice_map: dict = None,
                                voice_name: str = None, tts_speed: float = 1.2) -> list:
    """
    Tạo file MP3 song song cho tất cả subtitle segment.

    Args:
        subtitles: list các segment có 'translation', 'speaker', 'start', 'end'
        output_dir: thư mục output
        provider: 'edge' (mặc định, miễn phí) hoặc 'google' (cao cấp)
        voice_map: dict ánh xạ Speaker -> giọng đọc cụ thể (tùy chọn)
        voice_name: giọng đọc đồng nhất áp dụng cho toàn bộ video (tắt phân vai)

    Returns:
        list segment với thêm key 'audio_path', 'tts_duration'
    """
    provider_label = "Gemini TTS" if provider == "gemini" else ("Google Cloud TTS" if provider == "google" else "edge-tts")
    concurrency = TTS_CONCURRENCY.get(provider, 5)
    logger.info(f"Generating TTS for {len(subtitles)} segments [{provider_label}] ({concurrency} concurrent, speed={tts_speed}x)...")
    logger.info(f"DEBUG: provider={provider}, voice_map={voice_map}, voice_name={voice_name}, tts_speed={tts_speed}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Chạy async event loop
    loop = asyncio.new_event_loop()
    try:
        updated_subtitles, google_failures = loop.run_until_complete(
            _generate_tts_concurrent(subtitles, output_dir, provider, voice_map, voice_name, tts_speed)
        )
    finally:
        loop.close()
    
    logger.info(f"TTS done: {len(updated_subtitles)}/{len(subtitles)} segments, {google_failures} failed")
    
    if provider in ("google", "gemini") and google_failures > 0:
        logger.error(f"{provider_label}: {google_failures}/{len(subtitles)} segments FAILED. NO FALLBACK.")
    
    return updated_subtitles
