import os
import platform
import stat

from utils.logger import create_folder_if_needed

if platform.system() == "Windows":
    import ctypes.wintypes
    CSIDL_PERSONAL = 5  # My Documents
    SHGFP_TYPE_CURRENT = 0  # Get current, not default value
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf)
    MY_DOCUMENTS = buf.value
else:
    MY_DOCUMENTS = os.path.expanduser("~/Documents")

CERTABO_SAVE_PATH = os.path.join(MY_DOCUMENTS, "Certabo Saved Games")  # TODO: This should be somewhere else?
ENGINE_PATH = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "engines")
BOOK_PATH = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "books")

create_folder_if_needed(CERTABO_SAVE_PATH)
create_folder_if_needed(ENGINE_PATH)
create_folder_if_needed(BOOK_PATH)

if platform.system() == 'Windows':
    def get_engine_list():
        result_exe = []
        result_rom = []
        for filename in os.listdir(ENGINE_PATH):
            if filename == 'MessChess':
                roms = os.path.join(ENGINE_PATH, filename, 'roms')
                for rom in os.listdir(roms):
                    result_rom.append('rom-' + os.path.splitext(rom)[0])

            if filename.endswith('.exe'):
                result_exe.append(os.path.splitext(filename)[0])
        result_exe.sort()
        result_rom.sort()
        return result_exe + result_rom
else:
    def get_engine_list():
        result = []
        for filename in os.listdir(ENGINE_PATH):
            st = os.stat(os.path.join(ENGINE_PATH, filename))
            if st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                result.append(filename)
        result.sort()
        return result


def get_book_list():
    result = []
    for filename in os.listdir(BOOK_PATH):
        result.append(filename)
    result.sort()
    return result

