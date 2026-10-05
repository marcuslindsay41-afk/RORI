from pathlib import Path

from dotenv import load_dotenv

# Load the project-root .env for local development. Real environment variables take precedence.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
