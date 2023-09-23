from src.client import bot
from src.handlers import labelers


[bot.labeler.load(labeler) for labeler in labelers]
