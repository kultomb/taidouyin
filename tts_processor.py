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

# Giọng mặc định phân vai (female / male) - khóa giọng miền Bắc
_voice_list_female = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "female" and "HN" in info["label"]]
_voice_list_male   = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "male" and "HN" in info["label"]]
if not _voice_list_female:
    _voice_list_female = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "female"]
if not _voice_list_male:
    _voice_list_male = [v for v, info in ALL_GOOGLE_VOICES.items() if info["gender"] == "male"]

GOOGLE_VOICES = {
    "female": _voice_list_female[0] if _voice_list_female else "vi-VN-Neural2-A",
    "male":   _voice_list_male[0]   if _voice_list_male   else "vi-VN-Standard-B",
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
    tmp_path = input_path + ".tmp.mp3"
    result = _apply_atempo(input_path, tmp_path, speed, f"Speed up TTS {speed:.1f}x")
    if result == tmp_path and os.path.exists(tmp_path):
        os.replace(tmp_path, input_path)
    return input_path

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
    """Cắt khoảng lặng ở ĐẦU VÀ CUỐI file audio bằng FFmpeg silenceremove (không cắt ở giữa).
    Hỗ trợ cả MP3, WAV, PCM từ Gemini TTS.
    Sử dụng kỹ thuật areverse để xóa khoảng lặng ở cuối mà không ảnh hưởng đến phần giữa câu thoại.
    Ngưỡng -50dB đảm bảo không cắt phạm vào âm gió/âm nhẹ."""
    # Luôn re-encode ra MP3 để đảm bảo định dạng đồng nhất
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
        "-c:a", "libmp3lame", "-q:a", "2",
        "-ar", "44100",  # chuẩn hóa sample rate
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=15)
        # Chỉ coi là trim thành công nếu file output tồn tại và có dung lượng lớn hơn 0
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to trim silence for {input_path}: {e}")
        return False


# ============================================================
# TTS Providers
# ============================================================

class EdgeTTSProvider:
    """edge-tts: miễn phí, Microsoft Neural voices."""
    name = "edge"

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
        voice = voice_name if voice_name else get_edge_voice(speaker, voice_map)
        if tts_speed >= 1.0:
            rate_str = f"+{int((tts_speed - 1.0) * 100)}%"
        else:
            rate_str = f"-{int((1.0 - tts_speed) * 100)}%"
        logger.info(f"[edge-tts] '{text[:30]}...' -> {voice} (rate={rate_str})")
        async def _run():
            await edge_tts.Communicate(text, voice, rate=rate_str).save(output_path)
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

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
        from google.cloud import texttospeech
        voice_name_actual = voice_name if voice_name else get_google_voice(speaker, voice_map)
        logger.info(f"[Google TTS] '{text[:30]}...' -> {voice_name_actual} (speed={tts_speed})")

        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code="vi-VN",
            name=voice_name_actual,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=tts_speed,
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
    API_TIMEOUT = 60  # seconds — tránh treo vô hạn khi API không phản hồi

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

    def synthesize(self, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
        from google.genai import types

        voice_name_actual = pick_gemini_voice(speaker, voice_map, voice_name)
        logger.info(f"[Gemini TTS] '{text[:30]}...' -> {voice_name_actual}")

        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            temperature=0.0,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name_actual)
                )
            )
        )

        client = self._get_client()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                client.models.generate_content,
                model="gemini-2.5-flash-preview-tts",
                contents=[text],
                config=config
            )
            try:
                response = future.result(timeout=self.API_TIMEOUT)
            except concurrent.futures.TimeoutError:
                raise Exception(
                    f"Gemini TTS API timeout after {self.API_TIMEOUT}s for voice='{voice_name_actual}'"
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

async def _synthesize_edge_async(text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
    """edge-tts async wrapper với cơ chế retry mạnh mẽ."""
    voice = voice_name if voice_name else get_edge_voice(speaker, voice_map)
    if tts_speed >= 1.0:
        rate_str = f"+{int((tts_speed - 1.0) * 100)}%"
    else:
        rate_str = f"-{int((1.0 - tts_speed) * 100)}%"
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            await edge_tts.Communicate(text, voice, rate=rate_str).save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return
            raise Exception("Output file empty or not created")
        except Exception as e:
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 3  # 3s, 6s, 9s, 12s
                logger.warning(f"[edge-tts] Retry {attempt+1}/{max_retries} after {delay}s for speaker='{speaker}': {e}")
                await asyncio.sleep(delay)
            else:
                logger.error(f"[edge-tts] FAILED after {max_retries} retries for speaker='{speaker}': {e}")
                raise

def _synthesize_google_sync(tts: GoogleTTSProvider, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
    """Google TTS sync wrapper với cơ chế retry mạnh mẽ."""
    import time as _time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            tts.synthesize(text, speaker, output_path, voice_map, voice_name, tts_speed)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return
            raise Exception("Output file empty or not created")
        except Exception as e:
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 3  # 3s, 6s, 9s, 12s
                logger.warning(f"[Google TTS] Retry {attempt+1}/{max_retries} after {delay}s for speaker='{speaker}': {e}")
                _time.sleep(delay)
            else:
                logger.error(f"[Google TTS] FAILED after {max_retries} retries for speaker='{speaker}': {e}")
                raise

def _synthesize_gemini_sync(tts: GeminiTTSProvider, text: str, speaker: str, output_path: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.0):
    """Gemini TTS sync wrapper với retry mạnh - KHÔNG đổi giọng, KHÔNG bỏ cuộc dễ."""
    import time as _time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            tts.synthesize(text, speaker, output_path, voice_map, voice_name, tts_speed)
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

TTS_PRONUNCIATION_MAP = {
    r"\bread\b": "rít",
    r"\bwrite\b": "rai",
    r"\bscsi\b": "ét xê ét ai",
    r"\berror\b": "e ro",
    r"\bauto\b": "o to",
    r"\bbackup\b": "bách ắp",
    r"\bfrp\b": "ép rờ pê",
    r"\bufs\b": "u ép ét",
    r"\bcpu\b": "xê pu",
    r"\bram\b": "ram",
    r"\brom\b": "rom",
    r"\bic\b": "ai xi",
    r"\bbox\b": "bốc",
    r"\bbypass\b": "bai pát",
    r"\btool\b": "tun",
    r"\blog\b": "lóc",
    r"\bdriver\b": "đơ rai vơ",
    r"\bport\b": "pọt",
    r"\breset\b": "ri xét",
    r"\bboot\b": "bút",
    r"\bmain\b": "men",
    r"\bfirmware\b": "phơm we",
    r"\bimei\b": "i mei",
    r"\bdump\b": "đăm",
    r"\bformat\b": "pho mát",
    r"\brecovery\b": "ri co vơ ri",
    r"\bmosfet\b": "mót phét",
    r"\bi2c\b": "ai hai xê",
    r"\bbga\b": "bê gờ a",
    r"\bemmc\b": "e mờ mờ xê",
    r"\bvbat\b": "vê bát",
    r"\bvph\b": "vê pê hát",
    r"\bvbus\b": "vê bút",
    r"\bactive\b": "ác típ",
    r"\bkey\b": "ki",
    r"\bfile\b": "phai",
    r"\bclick\b": "kích",
    r"\bselect\b": "xơ léc",
    r"\bok\b": "ô kê"
}

def load_tts_glossary() -> dict:
    """Tải từ điển phát âm tùy chỉnh từ file glossary_tts.txt nếu tồn tại."""
    import re
    custom_map = {}
    filename = "glossary_tts.txt"
    
    # Kiểm tra một số vị trí có thể chứa file
    possible_paths = [
        filename,
        os.path.join(os.getcwd(), filename),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    ]
    
    glossary_path = None
    for p in possible_paths:
        if os.path.exists(p):
            glossary_path = p
            break
            
    if glossary_path:
        try:
            with open(glossary_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    parts = line.split("=", 1)
                    key = parts[0].strip().lower()
                    val = parts[1].strip()
                    if key and val:
                        # Lưu dưới dạng định dạng regex nguyên từ (\bword\b)
                        pattern = r"\b" + re.escape(key) + r"\b"
                        custom_map[pattern] = val
            logger.info(f"Loaded {len(custom_map)} custom TTS pronunciations from {glossary_path}")
        except Exception as e:
            logger.warning(f"Failed to load custom TTS glossary: {e}")
            
    return custom_map

def normalize_text_for_tts(text: str) -> str:
    """Chuẩn hóa các thuật ngữ tiếng Anh chuyên ngành điện thoại để đọc chuẩn giọng thợ Việt.
    Hỗ trợ tải động từ file glossary_tts.txt để người dùng dễ dàng cập nhật thêm từ mới."""
    if not text:
        return ""
    import re
    
    # 1. Khởi tạo map mặc định
    full_map = dict(TTS_PRONUNCIATION_MAP)
    
    # 2. Tải động từ glossary_tts.txt
    custom_map = load_tts_glossary()
    full_map.update(custom_map)
    
    # 3. Tiến hành thay thế
    normalized = text
    for pattern, replacement in full_map.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
    return normalized

def batch_transliterate_for_tts(subtitles: list) -> list:
    """
    Sử dụng Gemini để chuyển đổi hàng loạt các câu phụ đề sang dạng phiên âm phát âm tiếng Việt
    cho tất cả các thuật ngữ tiếng Anh, chữ viết tắt, mã hiệu... trước khi chạy TTS.
    """
    import re
    texts = [sub.get("translation", "").strip() for sub in subtitles]
    if not any(t for t in texts):
        return [sub.get("translation", "") for sub in subtitles]
        
    logger.info(f"🤖 Đang gửi {len(texts)} câu sang Gemini để phiên âm phát âm tiếng Việt hàng loạt...")
    
    batch_text = "\n---\n".join(
        f"[{i+1}] {t}" for i, t in enumerate(texts) if t
    )
    
    prompt = (
        "You are an expert Vietnamese voiceover assistant specialized in phone repair tutorials.\n"
        "Your task is to rewrite each Vietnamese sentence below so that all English words, technical acronyms, "
        "brand names, and codes (e.g. read, write, error, filled, backup, HS, SCSI, UFS, FRP, LDO, gear...) "
        "are converted into their natural Vietnamese phonetic pronunciations as spoken by Vietnamese technicians.\n\n"
        "CRITICAL RULES:\n"
        "1. Keep existing Vietnamese words exactly as they are. Only rewrite the English words and acronyms.\n"
        "2. Keep numbers and simple symbols. Convert letters and acronyms to their Vietnamese phonetic spellings (e.g. HS -> hát ét, UFS -> u ép ét, eMMC -> e mờ mờ xê, SCSI -> ét xê ét ai, read -> rít, write -> rai, filled -> phin, gear -> ghia, error -> e ro).\n"
        "3. Brand names must be pronounced naturally (e.g. Motorola -> mô tô rô la, Samsung -> sam sung).\n"
        "4. Return ONLY the rewritten lines, one per line, in the exact same order. No numbers, no markdown, no comments.\n\n"
        "# TEXT TO REWRITE:\n" + batch_text
    )
    
    try:
        from translator import get_vertex_client
        from google.genai import types
        client = get_vertex_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0.1)
        )
        if response and response.text:
            lines = [l.strip() for l in response.text.split("\n") if l.strip()]
            
            phonetic_texts = [""] * len(subtitles)
            j = 0
            for i, sub in enumerate(subtitles):
                text = sub.get("translation", "").strip()
                if text:
                    if j < len(lines):
                        # Loại bỏ số thứ tự [1] hoặc đầu dòng nếu Gemini vô tình trả về
                        cleaned_line = re.sub(r"^\[\d+\]\s*", "", lines[j]).strip()
                        phonetic_texts[i] = cleaned_line
                        j += 1
                    else:
                        phonetic_texts[i] = text
                else:
                    phonetic_texts[i] = ""
            
            logger.info("✅ Phiên âm phát âm tiếng Việt bằng Gemini thành công.")
            return phonetic_texts
    except Exception as e:
        logger.warning(f"⚠️ Không thể phiên âm bằng Gemini: {e}. Sẽ dùng bộ lọc từ điển cục bộ.")
        
    return None

async def _generate_tts_concurrent(subtitles: list, output_dir: str, provider: str, voice_map: dict = None, voice_name: str = None, tts_speed: float = 1.2) -> tuple:
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
    
    # 1. Gọi Gemini để phiên âm phát âm tiếng Việt hàng loạt trước khi chạy TTS
    loop = asyncio.get_event_loop()
    try:
        phonetic_texts = await loop.run_in_executor(
            None, batch_transliterate_for_tts, subtitles
        )
    except Exception as e:
        logger.warning(f"Failed to batch transliterate: {e}")
        phonetic_texts = None
    
    if provider == "gemini":
        tts = GeminiTTSProvider()
    elif provider == "google":
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
        
        # Chuẩn hóa văn bản đọc của TTS theo kiểu thợ Việt (vẫn giữ nguyên text phụ đề SRT gốc)
        if phonetic_texts and idx < len(phonetic_texts) and phonetic_texts[idx]:
            text_for_tts = phonetic_texts[idx]
        else:
            text_for_tts = normalize_text_for_tts(text)
        
        async with semaphore:
            success_segment = False
            loop = asyncio.get_event_loop()
            try:
                if speaker == "Mute" or speaker == "None":
                    from audio_processor import _generate_silence
                    dur = max(0.1, sub.get("end", 0) - sub.get("start", 0))
                    await loop.run_in_executor(
                        None, _generate_silence, file_path, dur
                    )
                elif provider == "gemini":
                    await loop.run_in_executor(
                        None, _synthesize_gemini_sync, tts, text_for_tts, speaker, file_path, voice_map, voice_name, tts_speed
                    )
                elif provider == "google":
                    await loop.run_in_executor(
                        None, _synthesize_google_sync, tts, text_for_tts, speaker, file_path, voice_map, voice_name, tts_speed
                    )
                else:
                    await _synthesize_edge_async(text_for_tts, speaker, file_path, voice_map, voice_name, tts_speed)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    success_segment = True
                else:
                    raise Exception("Output file was not generated or is empty.")
            except Exception as e:
                logger.error(f"[{provider}] FAILED segment {idx} (speaker='{speaker}', text='{text[:40]}...'): {e}")

            if success_segment:
                try:
                    if speaker != "Mute" and speaker != "None":
                        # Cắt bỏ khoảng lặng đầu/cuối của file âm thanh vừa tạo
                        trimmed_file_path = file_path + ".trimmed.mp3"
                        try:
                            success_trim = await loop.run_in_executor(
                                None, trim_silence, file_path, trimmed_file_path
                            )
                            if success_trim and os.path.exists(trimmed_file_path) and os.path.getsize(trimmed_file_path) > 0:
                                os.replace(trimmed_file_path, file_path)
                            else:
                                logger.warning(f"Trim silence failed or produced empty file for segment {idx}, using original untrimmed TTS")
                        except Exception as trim_e:
                            logger.warning(f"Trim silence error for segment {idx}, using original untrimmed TTS: {trim_e}")

                        # Apply speed factor for Gemini (Google and Edge native speed handles it)
                        if provider == "gemini" and abs(tts_speed - 1.0) > 0.01:
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
