import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

pre_paths = sys.path
sys.path.append(str(Path(sys.path[0]).joinpath('src')))
post_paths = sys.path

logger.info(pre_paths)
logger.info(post_paths)
logger.info(list(set(post_paths)-set(pre_paths)))
