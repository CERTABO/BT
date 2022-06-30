"""
Includes globals that are shared across modules
"""
import argparse

APPLICATION = 'MAIN'
VERSION = '06.11.2020'

parser = argparse.ArgumentParser()
parser.add_argument("--usbport", help='USB port to Certabo Board')
parser.add_argument("--btport", help='Bluetooth address to Certabo Server (RaspberryPi)')
parser.add_argument("--publish", help="URL to publish data")
parser.add_argument("--game-id", help="Game ID")
parser.add_argument("--game-key", help="Game key")
parser.add_argument("--robust", help="Robust", action="store_true")
parser.add_argument("--syzygy", help="Syzygy path")
parser.add_argument("--hide-cursor", help="Hide cursor", action="store_true")
parser.add_argument("--max-depth", help="Maximum depth", type=int, default=20)
parser.add_argument('--debug', help='Debug mode (additional options: {off, led, pystockfish, reading, analysis, fps})', nargs='*')
parser.add_argument('--port-not-strict', help='Whether find_port runs in strict mode', action='store_false')
# multiprocessing extra arguments (not used by us)
parser.add_argument('--multiprocessing-fork', nargs='*')

args = parser.parse_args()

DEBUG = True
DEBUG_LED = False
DEBUG_PYSTOCKFISH = False
DEBUG_READING = False
DEBUG_ANALYSIS = False
DEBUG_FPS = False
if args.debug is not None:
    for narg in args.debug:
        if narg == 'off':
            DEBUG = False
        elif narg == 'led':
            DEBUG_LED = True
        elif narg == 'pystockfish':
            DEBUG_PYSTOCKFISH = True
        elif narg == 'reading':
            DEBUG_READING = True
        elif narg == 'analysis':
            DEBUG_ANALYSIS = True
        elif narg == 'fps':
            DEBUG_FPS = True
        else:
            print(f'Debug optional narg not recognized: {narg}')
            print('Valid options are: {led, pystockfish}')
            raise SystemError

scr = None
x_multiplier = None
y_multiplier = None
xresolution = None
font_very_small = None
font_small = None
font = None
font_large = None
font_very_large = None

sprites = None
audiofiles = None

BTPORT = 10
