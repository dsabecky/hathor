import logging

# logging setup
logging.basicConfig(level=logging.INFO, format='\033[90m%(asctime)s \033[94m%(levelname)s     \033[35m%(name)s\033[0m %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_cogs = logging.getLogger('discord.cogs')
log_sys  = logging.getLogger('system')

log_chatgpt = logging.getLogger('chatgpt')
log_gamba   = logging.getLogger('gamba')
log_msg     = logging.getLogger('message')
log_music   = logging.getLogger('music')
log_voice   = logging.getLogger('voice')