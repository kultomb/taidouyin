import os
import json
import logging
from pathlib import Path
from google import genai
from google.genai import types, errors
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_not_exception_type

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
            "You are an expert video transcriber, translator, and subtitler. "
            "Analyze the video and audio input, transcribe the speech exactly, then translate it into Vietnamese. "
            "Divide the text into short segments (sentences/clauses) and determine the start and end timestamps in seconds "
            "for each segment based on both speech and visual actions (lip movements, screen events). "
            "Also identify the speaker for each segment (e.g. Speaker A, Speaker B)."
        )
    else:
        prompt = (
            "You are an expert audio transcriber, translator, and subtitler. "
            "Listen to the audio input and transcribe the speech exactly, then translate it into Vietnamese. "
            "Divide the text into short segments (sentences/clauses) and determine the start and end timestamps in seconds "
            "for each segment. Also identify the speaker for each segment (e.g. Speaker A, Speaker B)."
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
