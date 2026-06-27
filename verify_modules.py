import sys
import os
from google.genai import types

print("=== STARTING IMPORT AND INTEGRATION VERIFICATION ===")

# Test local imports
try:
    import downloader
    print("[OK] downloader.py imported successfully")
except Exception as e:
    print(f"[ERROR] downloader.py failed to import: {e}")
    sys.exit(1)

try:
    import audio_processor
    print("[OK] audio_processor.py imported successfully")
except Exception as e:
    print(f"[ERROR] audio_processor.py failed to import: {e}")
    sys.exit(1)

try:
    import translator
    print("[OK] translator.py imported successfully")
except Exception as e:
    print(f"[ERROR] translator.py failed to import: {e}")
    sys.exit(1)

try:
    import tts_processor
    print("[OK] tts_processor.py imported successfully")
except Exception as e:
    print(f"[ERROR] tts_processor.py failed to import: {e}")
    sys.exit(1)

try:
    import main
    print("[OK] main.py imported successfully")
except Exception as e:
    print(f"[ERROR] main.py failed to import: {e}")
    sys.exit(1)

# Test Vertex Client creation
print("\n=== TESTING VERTEX AI CLIENT INITIALIZATION & CONNECTIVITY ===")
try:
    client = translator.get_vertex_client()
    print("[OK] Vertex AI Client initialized successfully!")
    
    # Run a simple content generation request to test credentials and connection
    print("Testing connection with a simple API call...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hello, reply OK.",
        config=types.GenerateContentConfig(
            max_output_tokens=50,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )
    print(f"[OK] Connection test response text: {response.text.strip()}")
    
except Exception as e:
    print(f"[ERROR] Connection test failed: {e}")
    sys.exit(1)

print("\n=== ALL SYSTEM CHECKS PASSED SUCCESSFULLY ===")
