import logging
import logging.handlers
import os
from types import SimpleNamespace

import appdirs

# TODO:Where should this be?
try:
    import cfg
except ImportError:
    cfg = SimpleNamespace()
    cfg.DEBUG = False
    cfg.DEBUG_LED = False
    cfg.DEBUG_READING = False
    cfg.APPLICATION = 'UNKNOWN'
    cfg.VERSION = '10.04.2020'
    cfg.args = SimpleNamespace()
    cfg.args.usbport = None
    cfg.args.port_not_strict = True

CERTABO_DATA_PATH = appdirs.user_data_dir("GUI", "Certabo")


def set_logger():
    # TODO: Allow console to have lower level than log file
    log_format = "%(asctime)s:%(module)s:%(message)s"

    # Display debug messages in console only if DEBUG == True
    if cfg.DEBUG:
        logging.basicConfig(level='DEBUG', format=log_format)

    # Set logfile settings
    filehandler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(CERTABO_DATA_PATH, f"certabo_{cfg.APPLICATION}.log"), backupCount=12)
    filehandler.suffix = "%Y-%m-%d-%H"
    filehandler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(filehandler)
    logging.getLogger().setLevel('DEBUG' if cfg.DEBUG or cfg.DEBUG_LED else 'INFO')

    logging.debug('#' * 75)
    logging.debug('#' * 75)
    logging.info(f'{cfg.APPLICATION} application launched')
    logging.info(f'Version: {cfg.VERSION}')
    logging.info(f'Arguments: {cfg.args}')


def create_folder_if_needed(path):
    os.makedirs(path, exist_ok=True)


create_folder_if_needed(CERTABO_DATA_PATH)
