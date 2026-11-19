from dotenv import load_dotenv
import os


load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")

ALLOWED_EXTENSIONS = [".pdf", ".txt"]
MAX_FILE_SIZE_MB = 10  # Maximum file size in megabytes
UPLOAD_DIR = "uploads"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # no longer used, kept for reference

# Tokens.bd (OpenAI-compatible LLM API)
TOKENS_API_KEY = os.getenv("TOKENS_API_KEY")
TOKENS_BASE_URL = os.getenv("TOKENS_BASE_URL", "https://tokens.bd/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "google/gemini-3.8-flash")