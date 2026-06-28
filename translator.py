import os
import json
import logging
from pathlib import Path
from google import genai
from google.genai import types, errors
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type
from faster_whisper import WhisperModel

logger = logging.getLogger("douyin_translator")

# Credentials từ environment variables (không hardcode)
# GOOGLE_APPLICATION_CREDENTIALS: path tới JSON key
# GOOGLE_CLOUD_PROJECT: project ID (tùy chọn, đọc từ JSON nếu không có)
# GOOGLE_CLOUD_LOCATION: region (mặc định us-central1)
JSON_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "full-video-499000")
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

class TranslateError(Exception):
    pass

class StopTask(Exception):
    pass

NO_RETRY_EXCEPT = (StopTask,)

def get_vertex_client(json_path: str = JSON_PATH) -> genai.Client:
    """Creates a Vertex AI GenAI Client using a service account JSON file."""
    if not os.path.exists(json_path):
        logger.error(f"Service account file not found at {json_path}")
        raise StopTask(f"Service account file not found at {json_path}")
        
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = json_path
    
    # Read project ID dynamically from JSON key
    try:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        project_id = data.get("project_id", PROJECT_ID)
        logger.info(f"Loaded credentials for project: {project_id}")
    except Exception as e:
        logger.warning(f"Could not read project ID from JSON file, using default: {PROJECT_ID}. Error: {e}")
        project_id = PROJECT_ID
        
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=LOCATION,
    )

@retry(
    retry=retry_if_not_exception_type(NO_RETRY_EXCEPT),
    stop=stop_after_attempt(3),
    wait=wait_fixed(3),
    reraise=True
)
def transcribe_and_translate_audio(client: genai.Client, audio_path: str) -> dict:
    """
    Sends the audio or video file to Gemini 2.5 Flash, transcribing and translating it directly into Vietnamese.
    Returns a dictionary matching the subtitle schema.
    """
    logger.info(f"Sending file to Gemini for ASR and Translation: {audio_path}")
    
    if not os.path.exists(audio_path):
        raise StopTask(f"File not found: {audio_path}")
        
    # Read file bytes
    try:
        file_bytes = Path(audio_path).read_bytes()
    except Exception as e:
        raise StopTask(f"Failed to read file: {e}")
        
    # Detect mime type based on extension
    ext = Path(audio_path).suffix.lower()
    if ext == ".mp3":
        mime_type = "audio/mp3"
    elif ext == ".wav":
        mime_type = "audio/wav"
    elif ext in (".ogg", ".oga"):
        mime_type = "audio/ogg"
    elif ext == ".mp4":
        mime_type = "video/mp4"
    else:
        mime_type = "audio/mpeg"
        
    if mime_type.startswith("video/"):
        prompt = (
            "You are an expert video transcriber, translator, and subtitler specialized in Vietnamese dubbing. "
            "Analyze the video and audio input together. Transcribe the speech exactly, then translate it into natural, fluent Vietnamese suitable for spoken dubbing.\n\n"
            "CRITICAL DUBBING TRANSLATION RULES:\n"
            "1. Keep similar speaking duration as the original.\n"
            "2. The Vietnamese translation length must not exceed the original by more than 10% in syllable count.\n"
            "3. Prefer short, natural, spoken Vietnamese over literal translation. Do not use overly formal or literary terms.\n\n"
            "CRITICAL SEGMENTATION RULES:\n"
            "1. Divide text into short segments (1-2 sentences each, max 8 seconds per segment).\n"
            "2. NEVER split a segment in the middle of a visual action (gesture, scene change, object interaction).\n"
            "3. Align segment boundaries with natural pauses in speech AND visual action boundaries.\n"
            "4. When there is a clear visual event (someone points, a product is shown, scene transitions), start a new segment at that exact moment.\n"
            "5. Ensure each segment's start timestamp precisely matches the first lip movement or visual action onset.\n"
            "6. Ensure each segment's end timestamp matches when the action/speech naturally concludes.\n"
            "7. For overlapping speech with actions, prioritize the action boundary for segmentation.\n\n"
            "Identify the speaker for each segment (e.g. Speaker A, Speaker B)."
        )
    else:
        prompt = (
            "You are an expert audio transcriber, translator, and subtitler specialized in Vietnamese dubbing. "
            "Listen to the audio input and transcribe the speech exactly, then translate it into natural, fluent Vietnamese suitable for spoken dubbing.\n\n"
            "CRITICAL DUBBING TRANSLATION RULES:\n"
            "1. Keep similar speaking duration as the original.\n"
            "2. The Vietnamese translation length must not exceed the original by more than 10% in syllable count.\n"
            "3. Prefer short, natural, spoken Vietnamese over literal translation. Do not use overly formal or literary terms.\n\n"
            "CRITICAL SEGMENTATION RULES:\n"
            "1. Divide text into short segments (1-2 sentences each, max 8 seconds per segment).\n"
            "2. NEVER split a segment in the middle of a natural speech pause or sentence boundary.\n"
            "3. Align segment boundaries with natural pauses, breath points, and tone shifts in the speaker's voice.\n"
            "4. When the speaker changes tone, pace, or topic, start a new segment.\n"
            "5. Ensure each segment's start timestamp precisely matches the first audible word.\n"
            "6. Ensure each segment's end timestamp matches when the speech naturally concludes (not just when sound stops).\n"
            "7. Avoid segments shorter than 1.5 seconds or longer than 8 seconds.\n\n"
            "Identify the speaker for each segment (e.g. Speaker A, Speaker B)."
        )
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "subtitles": {
                "type": "ARRAY",
                "description": "List of all translated and timed subtitle segments",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "NUMBER", "description": "Start time in seconds of the spoken segment"},
                        "end": {"type": "NUMBER", "description": "End time in seconds of the spoken segment"},
                        "speaker": {"type": "STRING", "description": "Speaker label (e.g., Speaker A)"},
                        "text": {"type": "STRING", "description": "Original transcript in the native language (Chinese)"},
                        "translation": {"type": "STRING", "description": "Vietnamese translation of the transcript"}
                    },
                    "required": ["start", "end", "speaker", "text", "translation"]
                }
            }
        },
        "required": ["subtitles"]
    }
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.2,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        )
        
        if not response.text:
            raise TranslateError("Empty response received from Gemini.")
            
        parsed_result = json.loads(response.text)
        logger.info(f"Successfully received {len(parsed_result.get('subtitles', []))} subtitle segments from Gemini.")
        return parsed_result
        
    except errors.APIError as e:
        logger.error(f"Vertex API Error: code={e.code}, message={e.message}")
        if e.code in (400, 403, 404, 500):
            raise StopTask(f"Fatal API error: {e.message}")
        if e.code == 429:
            raise TranslateError("Rate limit / Quota exceeded, retrying...")
        raise TranslateError(e.message)
    except Exception as e:
        logger.error(f"Error during Gemini processing: {str(e)}")
        if isinstance(e, StopTask):
            raise e
        raise TranslateError(f"Unexpected error: {str(e)}")


@retry(
    retry=retry_if_not_exception_type(NO_RETRY_EXCEPT),
    stop=stop_after_attempt(3),
    wait=wait_fixed(3),
    reraise=True
)
def ocr_and_translate_video(client: genai.Client, video_path: str) -> dict:
    """
    Sends the cropped video file to Gemini 2.5 Flash, performing OCR on hardcoded subtitles
    and translating them into Vietnamese.
    Returns a dictionary matching the subtitle schema.
    """
    logger.info(f"Sending cropped video to Gemini for OCR and Translation: {video_path}")
    
    if not os.path.exists(video_path):
        raise StopTask(f"File not found: {video_path}")
        
    try:
        file_bytes = Path(video_path).read_bytes()
    except Exception as e:
        raise StopTask(f"Failed to read file: {e}")
        
    prompt = (
        "You are an expert video OCR tool, subtitle extractor, and translator specialized in Vietnamese dubbing.\n"
        "Analyze the visual content of the video input and perform OCR on the hardcoded text (subtitles) appearing on screen.\n\n"
        "CRITICAL TIMESTAMP RULES (visual-based, must match video frame-by-frame):\n"
        "1. Identify the EXACT frame number when each subtitle FIRST APPEARS on screen → start timestamp.\n"
        "2. Identify the EXACT frame number when each subtitle DISAPPEARS from screen → end timestamp.\n"
        "3. Do NOT use audio for timestamps - rely purely on visual subtitle appearance/disappearance.\n"
        "4. If subtitles have fade-in/fade-out transitions, use the frame where text is fully visible / fully gone.\n"
        "5. Ensure NO gap or overlap between consecutive subtitle segments on screen.\n"
        "6. If the subtitle stays on screen while the speaker pauses, extend the end time accordingly.\n\n"
        "For each subtitle segment:\n"
        "- Transcribe the native Chinese text exactly (fix typos if possible).\n"
        "- Translate into natural, fluent Vietnamese suitable for dubbing.\n"
        "  CRITICAL DUBBING TRANSLATION RULES:\n"
        "  1. Keep similar speaking duration as the original.\n"
        "  2. The Vietnamese translation length must not exceed the original by more than 10% in syllable count.\n"
        "  3. Prefer short, natural, spoken Vietnamese over literal translation. Do not use overly formal or literary terms.\n\n"
        "- Identify the speaker if clear, or default to 'Speaker A'.\n\n"
        "Segments MUST be sorted chronologically by start time."
    )
    
    schema = {
        "type": "OBJECT",
        "properties": {
            "subtitles": {
                "type": "ARRAY",
                "description": "List of all OCR-extracted and translated subtitle segments",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "NUMBER", "description": "Start time in seconds of the subtitle appearance"},
                        "end": {"type": "NUMBER", "description": "End time in seconds of the subtitle disappearance"},
                        "speaker": {"type": "STRING", "description": "Speaker label (e.g., Speaker A)"},
                        "text": {"type": "STRING", "description": "Original transcript from OCR in Chinese"},
                        "translation": {"type": "STRING", "description": "Vietnamese translation of the transcript"}
                    },
                    "required": ["start", "end", "speaker", "text", "translation"]
                }
            }
        },
        "required": ["subtitles"]
    }
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=file_bytes, mime_type="video/mp4"),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        )
        
        if not response.text:
            raise TranslateError("Empty response received from Gemini.")
            
        parsed_result = json.loads(response.text)
        logger.info(f"Successfully received {len(parsed_result.get('subtitles', []))} OCR subtitle segments from Gemini.")
        return parsed_result
        
    except errors.APIError as e:
        logger.error(f"Vertex API Error during OCR: code={e.code}, message={e.message}")
        if e.code in (400, 403, 404, 500):
            raise StopTask(f"Fatal API error: {e.message}")
        if e.code == 429:
            raise TranslateError("Rate limit / Quota exceeded, retrying...")
        raise TranslateError(e.message)
    except Exception as e:
        logger.error(f"Error during Gemini OCR processing: {str(e)}")
        if isinstance(e, StopTask):
            raise e
        raise TranslateError(f"Unexpected error: {str(e)}")


_whisper_model = None

def get_whisper_model() -> WhisperModel:
    """Lazy initializer and caching for the faster-whisper WhisperModel."""
    global _whisper_model
    if _whisper_model is None:
        logger.info("Initializing Local Whisper model (large-v3)...")
        try:
            _whisper_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
            logger.info("Loaded WhisperModel on GPU (CUDA)")
        except Exception as e:
            logger.warning(f"Failed to load WhisperModel on CUDA ({e}), falling back to CPU (int8)")
            try:
                _whisper_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
                logger.info("Loaded WhisperModel on CPU (int8)")
            except Exception as cpu_e:
                logger.error(f"Failed to load WhisperModel on CPU ({cpu_e})")
                raise cpu_e
    return _whisper_model

def transcribe_audio_local_whisper(audio_path: str) -> dict:
    """
    Transcribes the audio file offline using Local Whisper.
    Returns a dictionary matching the subtitle schema.
    """
    logger.info(f"Sending audio file to Local Whisper: {audio_path}")
    if not os.path.exists(audio_path):
        raise StopTask(f"File not found: {audio_path}")
        
    try:
        model = get_whisper_model()
        segments, info = model.transcribe(
            audio_path,
            language="zh",
            beam_size=5,
            word_timestamps=True,
            vad_filter=False
        )
        
        subtitles = []
        for segment in segments:
            subtitles.append({
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "speaker": "Speaker A",
                "text": segment.text.strip(),
                "translation": ""
            })
            
        logger.info(f"Successfully transcribed {len(subtitles)} segments using Local Whisper.")
        return {"subtitles": subtitles}
    except Exception as e:
        logger.error(f"Error during Local Whisper processing: {str(e)}")
        if isinstance(e, StopTask):
            raise e
        raise TranslateError(f"Local Whisper error: {str(e)}")

