import logging
import sys
import os

root = logging.getLogger()
log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO")) if hasattr(logging, os.getenv("LOG_LEVEL", "INFO")) else logging.INFO
root.setLevel(log_level)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)