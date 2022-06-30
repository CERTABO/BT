import logging
import os
import pickle
import queue
import time
from collections import Counter, deque

import chess

from utils.logger import cfg, CERTABO_DATA_PATH
from utils import usbtool

FEN_SPRITE_MAPPING = {"b": "black_bishop",
                      "k": "black_king",
                      "n": "black_knight",
                      "p": "black_pawn",
                      "q": "black_queen",
                      "r": "black_rook",
                      "B": "white_bishop",
                      "K": "white_king",
                      "N": "white_knight",
                      "P": "white_pawn",
                      "Q": "white_queen",
                      "R": "white_rook", }
COLUMNS_LETTERS = "a", "b", "c", "d", "e", "f", "g", "h"
COLUMNS_LETTERS_REVERSED = tuple(reversed(COLUMNS_LETTERS))


class BoardReader:
    def __init__(self, portname):
        self.queue = usbtool.QUEUE_FROM_USBTOOL

        self.data_history_depth = 3
        self.data_history_pointer = 0
        self.data_history_counter = 0
        self.data_history = [None] * self.data_history_depth
        self.last_update_time = time.time()

        self.calibration_samples_n = 15
        self.calibration_data_history_counter = 0
        self.calibration_samples = deque(maxlen=self.calibration_samples_n)

        self.board_fen = chess.Board().board_fen()
        self.counter = Counter()

        self.needs_calibration = False
        self.default_missing_piece = '.'
        self.ignore_missing = True
        self.code_mapping_order = ('p', 'r', 'n', 'b', 'k', 'q', 'P', 'R', 'N', 'B', 'K', 'Q')
        self.calibration_file = f'calibration-{portname.replace("/","").replace(":","")}.bin'
        self.calibration_filepath = os.path.join(CERTABO_DATA_PATH, self.calibration_file)
        self.code_mapping = {}
        self.load_piece_codes()
        self.cell_slice_mapping = [slice(cell * 5, cell * 5 + 5) for cell in range(64)]

    def load_piece_codes(self):
        mapping = dict()
        if not os.path.exists(self.calibration_filepath):
            logging.info('No calibration file detected: creating new file')
            self.needs_calibration = True
            pickle.dump({}, open(self.calibration_filepath, "wb"))

        logging.info(f'Loading calibration file: {self.calibration_filepath}')
        data = pickle.load(open(self.calibration_filepath, 'rb'))
        for letter, piece in zip(self.code_mapping_order, data):
            for piece_variation in piece:
                key = tuple(str(c) for c in piece_variation)
                mapping[key] = letter
        mapping[('0', '0', '0', '0', '0')] = '.'
        self.code_mapping = mapping

    def data_to_fen(self):
        data_history = [data[1:].split(' ') for data in self.data_history if data is not None]
        # Get board pieces from USB data
        board = []
        for cell_range in self.cell_slice_mapping:
            sample = (self.code_mapping.get(tuple(sample[cell_range]), self.default_missing_piece) for sample in data_history)
            self.counter.update(sample)
            most_common_code = self.counter.most_common(1)[0][0]
            board.append(most_common_code)
            self.counter.clear()

        # Convert to FEN
        FEN = ''
        for row in range(8):
            empty = 0
            for col in range(8):
                piece = board[row * 8 + col]
                # if piece == 'noise':
                #     piece = self.default_missing_piece

                if piece == '.':
                    empty += 1
                else:
                    if empty > 0:
                        FEN += str(empty)
                        empty = 0
                    FEN += piece
            if empty > 0:
                FEN += str(empty)
            if row < 7:
                FEN += r'/'

        if cfg.DEBUG_READING:
            if self.board_fen != FEN:
                new_update_time = time.time()
                diff_update_time = (new_update_time - self.last_update_time) * 1000
                logging.debug(f'UsbReader: computing FEN -> board CHANGED - {FEN} in {diff_update_time:.0f}ms')
                self.last_update_time = new_update_time
            else:
                logging.debug('UsbReader: computing FEN -> board not changed')
        self.board_fen = FEN

    def update(self):
        # TODO: Add timer and log when board cannot be read for too long
        changed = False
        new_data = False
        while True:
            try:
                data = self.queue.get_nowait()
                new_data = True

                # Check if data stream is different than any other saved in the history
                for _ in range(self.data_history_depth):

                    self.data_history_pointer += 1
                    if self.data_history_pointer >= self.data_history_depth:
                        self.data_history_pointer = 0

                    if not self.data_history[self.data_history_pointer] == data:
                        # If it is replace it,
                        # and break out of loop to avoid rewriting more than one entry in the history
                        self.data_history[self.data_history_pointer] = data
                        changed = True
                        break

            except queue.Empty:
                if new_data:
                    # This is used for calibration, to know when a new sample was obtained
                    self.data_history_counter = (self.data_history_counter + 1) % 64  # Limit number range to 64 values

                if changed:
                    self.data_to_fen()
                return

    def read_board(self, rotate180=False, update=True):
        if update:
            self.update()

        if rotate180:
            return self.board_fen[::-1]
        return self.board_fen

    def do_calibration(self, new_setup, verbose=False):
        # STEP 1) Combine data and find most common codes per cell
        data_history = [data[1:].split(' ') for data in self.calibration_samples if data is not None]

        board_reading = []
        for n_cell, cell_range in enumerate(self.cell_slice_mapping):
            cell_readings = []

            cell_id = COLUMNS_LETTERS[n_cell % 8] + str(8 - n_cell // 8)
            if verbose:
                logging.info(f"\n    {cell_id} samples:")

            for sample in data_history:
                cell_readings.append(tuple(sample[cell_range]))
                if verbose:
                    logging.info(sample[cell_range])

            self.counter.update(cell_readings)
            most_common = self.counter.most_common(1)[0][0]
            self.counter.clear()

            board_reading.extend(most_common)
            if verbose:
                logging.info(f"\n   Final code for {cell_id}: {most_common}")

        board_reading = [int(val) for val in board_reading]

        # --------------------------------------------------------------------------------------------------------------
        # STEP 2) Save codes obtained from board_reading

        def add_mapping(key, cell_index):
            code = board_reading[self.cell_slice_mapping[cell_index]]

            # Do not add empty or repeated codes
            if sum(code) and (code not in calibration_mapping[key]):

                # Check whether code was already in calibration mapping (for another piece type)
                if any(code in piece_codes for piece_codes in calibration_mapping.values()):
                    logging.warning(f'Piece code {code} was previously assigned to another piece! A full setup calibration may be necessary!')

                calibration_mapping[key].append(code)
                if not new_setup:
                    logging.info(f'Added new piece {key} with code: {code}')

        # Create empty calibration mapping
        calibration_mapping = {letter: [] for letter in FEN_SPRITE_MAPPING.keys()}

        # Populate with old info if doing "add_piece"
        if not new_setup:
            # Convert code_mapping (code -> piece) to calibration_mapping (piece -> code)
            for code, piece in self.code_mapping.items():
                # Skip empty square
                if piece == '.':
                    continue
                code_int_list = [int(num) for num in code]
                calibration_mapping[piece].append(code_int_list)

        for i in range(8):
            add_mapping('p', 8 + i)
            add_mapping('P', 48 + i)

        add_mapping('r', 0)
        add_mapping('r', 7)
        add_mapping('R', 56)
        add_mapping('R', 63)

        add_mapping('n', 1)
        add_mapping('n', 6)
        add_mapping('N', 57)
        add_mapping('N', 62)

        add_mapping('b', 2)
        add_mapping('b', 5)
        add_mapping('B', 58)
        add_mapping('B', 61)

        add_mapping('q', 3)
        add_mapping('Q', 59)
        add_mapping('q', 19)  # Spare queen
        add_mapping('Q', 43)  # Spare queen

        add_mapping('k', 4)
        add_mapping('K', 60)

        calibration_data = [calibration_mapping[key] for key in self.code_mapping_order]
        pickle.dump(calibration_data, open(self.calibration_filepath, "wb"))

        if new_setup:
            logging.info(f'Calibration: New mapping obtained:')
            for items in calibration_mapping.items():
                logging.info(str(items))

    def calibration(self, new_setup, verbose=False):
        # If there was a new sample since last call, save it to calibration
        if self.calibration_data_history_counter != self.data_history_counter:
            self.calibration_samples.append(self.data_history[self.data_history_pointer])
            self.calibration_data_history_counter = self.data_history_counter

        if len(self.calibration_samples) >= self.calibration_samples_n:
            logging.info("Calibration: Enough samples for averaging")
            self.do_calibration(new_setup, verbose)
            self.needs_calibration = False

            # Reset calibration readings
            self.calibration_samples.clear()

            # Update reading
            self.load_piece_codes()
            self.data_to_fen()
            logging.info('Calibration: completed successfully')
            return True

        return False

    @property
    def ignore_missing(self):
        return self._ignore_missing

    @ignore_missing.setter
    def ignore_missing(self, value):
        self._ignore_missing = value
        default_missing_piece = 'X' if not value else '.'
        if default_missing_piece != self.default_missing_piece:
            logging.info(f'Ignore missing: {value}')
            self.default_missing_piece = default_missing_piece


class LedWriter:
    def __init__(self):
        self.queue_to_usbtool = usbtool.QUEUE_TO_USBTOOL
        self.default_messages = {
            'all': [255] * 8,
            'none': [0] * 8,
            'start': [255, 255, 0, 0, 0, 0, 255, 255],
            'error': [0, 0, 0, 24, 24, 0, 0, 0],
            'corners': LedWriter.squares2led(['a1', 'a8', 'h1', 'h8']),
            'corner': LedWriter.squares2led(['a8']),
            'center': LedWriter.squares2led(['d4', 'e4', 'd5', 'e5']),
            'thinking': LedWriter.squares2led(['d4', 'e4', 'd5', 'e5']),
            'setup': [255, 255, 8, 0, 0, 8, 255, 255],
        }

        self.last_message = None

        self.last_flash_message = None
        self.flash_frequency = 1  # seconds
        self.flash_clock = None
        self.counter = 0

        self.last_misplaced_comparison = None
        self.last_misplaced_message = None
        self.misplaced_wait_time = 3  # seconds
        self.misplaced_clock = None

    def flash_leds(self, message, rotate180=False):
        # New message
        if self.last_flash_message != message:
            self.last_flash_message = message
            self.flash_clock = time.time()
            self.counter = 0
            if cfg.DEBUG_LED:
                logging.debug(f'LedManager: New flash - {message}')
            self.set_leds(message)
            return

        # Flash message on/off every 1 second
        elapsed_time = time.time()
        if elapsed_time - self.flash_clock > self.flash_frequency:
            self.flash_clock = elapsed_time
            self.counter += 1
            message = (self.last_flash_message, 'none')[self.counter % 2]
            if cfg.DEBUG_LED:
                logging.debug(f'LedManager: repeated flash - {self.last_flash_message} -> {message}')
            self.set_leds(message, rotate180)

    def set_leds(self, message='none', rotate180=False):
        if message != self.last_message:
            self.last_message = message
            # If text is given try to retrieve default message, otherwise assume square information was passed
            try:
                message = self.default_messages[message]
            except (KeyError, TypeError) as e:
                message = self.squares2led(message, rotate180)

            # message = [ord(d) for d in message]
            if cfg.DEBUG_LED:
                logging.debug(f'LedManager: got message - {self.last_message}')
                logging.debug(f'LedManager: sending to usbtool - {message}, {len(message)}')

            self.queue_to_usbtool.put(bytes(message))
            time.sleep(.001)

    @staticmethod
    def squares2led(squares, rotate180=False):
        """
        Converts list of squares to Certabo binary led encoding
        e.g., ['e2', 'e4'] = [0, 0, 0, 0, 16, 0, 16, 0] -> '\x00\x00\x00\x00\x10\x00\x10\x00'

        Accepts alternative string input (eg., 'e2' or even move string 'e2e4')
        Does not recognize move string inside list (e.g., ['e2e4'])
        """

        def _square2certabo(square, rotate180=False):
            """
            Converts a chess position code (e.g., e2) to the respective Certabo led code (e.g., led[6] = 16)
            """
            if rotate180:
                col = COLUMNS_LETTERS_REVERSED.index(square[0])
                row = 9 - int(square[1])
            else:
                col = COLUMNS_LETTERS.index(square[0])
                row = int(square[1])

            return 8 - row, 2 ** col

        # If single string was given assume a single square or move was passed
        if type(squares) == str:
            # Assume single square and force tuple
            if len(squares) < 4:
                led_positions = (_square2certabo(squares, rotate180),)
            # Assume move
            else:
                led_positions = (_square2certabo(squares[i: i+2], rotate180) for i in (0, 2))
        # Otherwise assume a list of squares was given
        else:
            # If list contains only one item, force tuple
            if len(squares) == 1:
                led_positions = (_square2certabo(squares[0], rotate180), )
            else:
                led_positions = (_square2certabo(square, rotate180) for square in set(squares))

        leds = [0] * 8
        for row, col in led_positions:
            leds[row] += col

        return leds

    def highlight_misplaced_pieces(self, physical_board_fen, virtual_board, rotate180=False, suppress_leds=False):
        """
        This functions finds pieces differences between the physical board fen and virtual chess.Chessboard
        Having found these difference it will wait a few seconds before actually highlighting the leds
        If leds are highlighted it returns True, otherwise returns None
        """
        boards_fens = physical_board_fen+virtual_board.fen()

        # If this comparison was already performed and enough time passed: highlight leds
        if boards_fens == self.last_misplaced_comparison:
            if time.time() - self.misplaced_clock > self.misplaced_wait_time:
                if not suppress_leds:
                    self.set_leds(self.last_misplaced_message, rotate180)
                return True

        # Otherwise find which leds should be highlighted
        else:
            try:
                temp_board = chess.Board()
                temp_board.set_board_fen(physical_board_fen)
            except ValueError:
                logging.error('Corrupt FEN from physical board')
            else:  # No Exception
                diffs = [chess.SQUARE_NAMES[square] for square in range(64) if
                         virtual_board.piece_at(square) != temp_board.piece_at(square)]
                if diffs:
                    if cfg.DEBUG_LED:
                        logging.debug(f'LedManager: found new board differences: {diffs}')
                        logging.debug(f'LedManager: waiting {self.misplaced_wait_time} seconds to highlight them')
                    self.last_misplaced_comparison = boards_fens
                    self.last_misplaced_message = diffs
                    self.misplaced_clock = time.time()
