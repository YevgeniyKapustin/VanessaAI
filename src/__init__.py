import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import Settings

load_dotenv()
config = Settings()
sys.path.append(str(Path(sys.path[0]).joinpath('..')))
