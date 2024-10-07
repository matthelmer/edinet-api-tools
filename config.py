# config.py
import os
from dotenv import load_dotenv

# load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

EDINET_API_KEY = os.environ.get('EDINET_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
