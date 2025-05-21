####################################################################
# Library & Modules
####################################################################

import logging
from rich.logging import RichHandler


####################################################################
# Logging Setup
####################################################################

rich_handler = RichHandler(
    rich_tracebacks=True,
    markup=True,
    show_path=False,
    show_time=True,
    show_level=True
)

formatter = logging.Formatter(fmt="%(message)s", datefmt="%m/%d %H:%M:%S")
rich_handler.setFormatter(formatter)

logging.basicConfig(
    level="INFO",
    handlers=[rich_handler],
)


####################################################################
# Loggers
####################################################################

log_cog = logging.getLogger('discord.cogs')
log_msg = logging.getLogger('message')
log_sys = logging.getLogger('system')