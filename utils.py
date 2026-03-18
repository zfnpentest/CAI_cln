import os
import cloudinary
import cloudinary.uploader
from openai import OpenAI
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# Cloudinary Setup
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# OpenRouter Setup
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

def upload_image(image_file):
    """Uploads character or user PFP to Cloudinary."""
    try:
        upload_result = cloudinary.uploader.upload(image_file)
        return upload_result['secure_url']
    except Exception as e:
        print(f"Cloudinary Error: {e}")
        return None

def get_ai_response(messages, model="google/gemini-2.0-flash-lite-preview-02-05:free"):
    """
    Primary: Gemini 2.0 Flash Lite (Low Latency / High Speed).
    Fallback: OpenRouter Auto-Free.
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            extra_headers={
                "HTTP-Referer": "http://localhost:8501", 
                "X-Title": "Zebra Private C.AI",
            }
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Flash model busy ({e}). Trying Auto-Router...")
        try:
            # Fallback to the general free router if Flash is down
            resp = client.chat.completions.create(model="openrouter/free", messages=messages)
            return resp.choices[0].message.content
        except Exception as f:
            return f"System: Connections are heavy right now. Please wait a moment. {f}"