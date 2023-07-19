import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(sys.path[0]).joinpath('src')))
