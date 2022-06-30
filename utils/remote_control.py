import logging

import pygame

from utils.get_books_engines import get_book_list, get_engine_list


class RemoteControl:
    def __init__(self, led_manager, on=True):
        self.led_manager = led_manager
        self.on = on
        self.wait_between_commands = 3000
        self.last_command_time = -self.wait_between_commands
        self.last_exit_command_time = -self.wait_between_commands
        self.exit_command = {'application': False, 'game': False}
        self.start_game = False
        self.can_calibrate = True

    @property
    def on(self):
        return self._on

    @on.setter
    def on(self, value):
        logging.info(f'Remote control: {value}')
        self._on = value

    def update(self, window, board_state, settings=None, virtual_board=None):
        # Do not update if exiting condition is observed
        if self.exit_command['application'] or not self.on:
            if window == 'home':
                return 'home', False
            elif window == 'new game':
                return settings, False
            elif window == 'game':
                return False, False
            elif window == 'thinking':
                return False

        if window == 'home':
            return self.home_window(board_state)
        elif window == 'new game':
            return self.new_game_window(board_state, settings)
        elif window == 'game':
            return self.game_window(board_state, settings, virtual_board)
        elif window == 'thinking':
            return self.thinking_window(board_state, virtual_board)

    def home_window(self, board_state):
        """
        Change to new game if spare queens are placed in D4/D5
        Start calibration if all pieces are in initial positions plus D3/D6
        """

        def hasNumbers(inputString):
            return any(char.isdigit() for char in inputString)

        # Check if spare queens are in D4/D5 -> New game
        if board_state in ('rnbqkbnr/pppppppp/8/3q4/3Q4/8/PPPPPPPP/RNBQKBNR',
                           'rnbqkbnr/pppppppp/8/3Q4/3q4/8/PPPPPPPP/RNBQKBNR'):
            logging.info('Remote control: New Game')
            self.last_command_time = pygame.time.get_ticks()
            self.led_manager.set_leds('corners')
            return 'new game', False

        # Check if any pieces are in ranks plus D3/D6 -> Calibration
        if self.can_calibrate:
            board_rows = board_state.split('/')
            if (all(len(board_rows[row]) == 8  # Check if top and bottom rows are full
                    and not hasNumbers(board_rows[row]) for row in (0, 1, 6, 7))  # Check if top and bottom rows have no integers
                    and all(board_rows[row] == '8' for row in (3, 4))  # Check if middle rows are empty
                    and board_rows[2][::2] == '34' and board_rows[5][::2] == '34'):  # Check if D3 and D6 are occupied

                logging.info(f'Remote control: Calibration command - board_state')
                self.last_command_time = pygame.time.get_ticks()
                self.led_manager.set_leds('corners')
                self.can_calibrate = False
                return 'home', True
        return 'home', False

    def new_game_window(self, board_state, settings):

        def row_0_to_71(row):
            '''
            Return integer between 0-71 depending on the placement of two queens in a row.
            Used for both engine and diffictulty choice
            '''
            # Case where there are two queens
            if 'Q' in row and 'q' in row:
                # Check how many empty squares are on the left side
                try:
                    leftmost_gap = int(row[0])
                except ValueError:
                    leftmost_gap = 0
                level = (16, 30, 42, 52, 60, 66, 70, 72)[leftmost_gap:leftmost_gap + 2]

                base = level[0]
                diff = (level[1] - level[0]) // 2

                # Check how many empty squares are on the right side
                try:
                    rightmost_gap = int(row[-1])
                except ValueError:
                    rightmost_gap = 0
                extra = diff - rightmost_gap

                # Check if black queen comes before white queen
                qs = [c for c in row if c in ('Q', 'q')]
                if qs[0] == 'q':
                    extra += diff
                num = base + extra

            # Simpler case with only one queen
            else:
                try:
                    num = 8 - int(row[-1])
                except ValueError:
                    num = 8
                if 'q' in row:
                    num += 8

            num -= 1
            return num

        # Do not update settings if last command happened recently
        if pygame.time.get_ticks() - self.last_command_time < self.wait_between_commands:
            if not self.start_game:
                self.led_manager.set_leds('corners')
            else:
                self.led_manager.flash_leds('corners')
            return settings, False

        if self.start_game:
            # Check if kings are in place when starting from board position
            if not settings['use_board_position'] or ('k' in board_state and 'K' in board_state):
                self.start_game = False
                return settings, True
            self.last_command_time = pygame.time.get_ticks()  # So it goes back to blinking next time it's called
            return settings, False

        self.led_manager.set_leds()
        old_settings = settings.copy()

        board_rows = board_state.split('/')
        static_rows = '/'.join(board_rows[0:2] + board_rows[-2:])
        # All normal pieces in place
        if static_rows == 'rnbqkbnr/pppppppp/PPPPPPPP/RNBQKBNR':
            # Only command with two queens in different rows is 'game start'
            if sum(len(board_row) == 3 for board_row in board_rows[2:-2]) == 2:
                # Game start
                if '/'.join(board_rows[3:5]).lower() == '4q3/4q3':
                    self.start_game = True
                    self.last_command_time = pygame.time.get_ticks()
                    # Give at least 20 seconds to remove kings, if using board
                    if settings['use_board_position']:
                        logging.info(f'Remote control: Starting game once both kings are placed')
                        self.last_command_time += 20000 - self.wait_between_commands
                    else:
                        logging.info(f'Remote control: Starting game')

            # Color, Flip board and Book
            elif 'Q' in board_rows[5] or 'q' in board_rows[5]:
                # Color and Flip board
                if board_rows[5][0] == 'Q':
                    settings['play_white'] = True
                elif board_rows[5][0] == 'q':
                    settings['play_white'] = False
                if board_rows[5].lower() in ('qq6', '1q6'):
                    settings['rotate180'] = False
                elif board_rows[5].lower() in ('q1q5', '2q5'):
                    settings['rotate180'] = True

                # Chess 960
                if board_rows[5].lower() == '3q4':
                    if board_rows[5][1] == 'Q':
                        settings['chess960'] = True
                    else:
                        settings['chess960'] = False

                # Book
                if board_rows[5][0] in ('4', '5', '6', '7') and board_rows[5][1] in ('Q', 'q'):
                    # If both Queens are placed, remove book
                    if 'Q' in board_rows[5] and 'q' in board_rows[5]:
                        settings['book'] = ''
                    else:
                        book_offset = int(board_rows[5][0]) - 4
                        if 'q' in board_rows[5]:
                            book_offset += 4
                        try:
                            settings['book'] = get_book_list()[book_offset]
                        except IndexError:
                            settings['book'] = ''

            # Use board position, Color to move, and default Time settings
            elif 'Q' in board_rows[4] or 'q' in board_rows[4]:
                if board_rows[4][0] == 'Q':
                    settings['use_board_position'] = False
                    settings['side_to_move'] = 'white'
                elif board_rows[4][0] == 'q':
                    settings['use_board_position'] = True

                if board_rows[4].lower() in ('qq6', '1q6'):
                    settings['side_to_move'] = 'white'
                elif board_rows[4].lower() in ('q1q5', '2q5'):
                    settings['side_to_move'] = 'black'

                else:
                    try:
                        index = 7 - int(board_rows[4][0])
                        if index < 5:
                            settings['time_constraint'] = ('classical', 'rapid', 'blitz', 'unlimited', 'custom')[index]
                    except ValueError:
                        pass

            # Engine difficulty
            elif 'Q' in board_rows[3] or 'q' in board_rows[3]:
                settings['difficulty'] = row_0_to_71(board_rows[3])

            # Engine
            elif 'Q' in board_rows[2] or 'q' in board_rows[2]:
                engine_index = row_0_to_71(board_rows[2])
                try:
                    settings['engine'] = get_engine_list()[engine_index]
                except IndexError:
                    settings['engine'] = 'stockfish'

        # Kings out of place
        elif static_rows in ('rnbq1bnr/pppppppp/PPPPPPPP/RNBQKBNR',
                             'rnbqkbnr/pppppppp/PPPPPPPP/RNBQ1BNR',
                             'rnbq1bnr/pppppppp/PPPPPPPP/RNBQ1BNR'):
            mins = None
            secs = None
            # White kings specifies minutes
            if 'K' in board_rows[5]:
                if board_rows[5] == 'K7':
                    settings['time_constraint'] = 'unlimited'
                else:
                    try:
                        mins = 7 - int(board_rows[5][-1])
                    except ValueError:
                        mins = 7
            elif 'K' in board_rows[4]:
                try:
                    mins = 15 - int(board_rows[4][-1])
                except ValueError:
                    mins = 15
            elif 'K' in board_rows[3]:
                try:
                    mins = 30 - int(board_rows[3][-1]) * 2
                except ValueError:
                    mins = 30
            elif 'K' in board_rows[2]:
                try:
                    mins = 110 - int(board_rows[2][-1]) * 10
                except ValueError:
                    mins = 120

            # black king specifies seconds
            if 'k' in board_rows[5]:
                try:
                    secs = 7 - int(board_rows[5][-1])
                except ValueError:
                    secs = 7
            elif 'k' in board_rows[4]:
                try:
                    secs = 15 - int(board_rows[4][-1])
                except ValueError:
                    secs = 15
            elif 'k' in board_rows[3]:
                try:
                    secs = 30 - int(board_rows[3][-1]) * 2
                except ValueError:
                    secs = 30
            elif 'k' in board_rows[2]:
                try:
                    secs = 110 - int(board_rows[2][-1]) * 10
                except ValueError:
                    secs = 120

            if mins is not None or secs is not None:
                settings['time_constraint'] = 'custom'
                if mins is not None:
                    settings['time_total_minutes'] = mins
                if secs is not None:
                    settings['time_increment_seconds'] = secs

        if settings != old_settings:
            self.last_command_time = pygame.time.get_ticks()

            for key, new, old in zip(settings.keys(), settings.values(), old_settings.values()):
                if not new == old:
                    logging.info(f'Remote control: Changed setting "{key}": {old} --> {new}')

        return settings, False

    def game_window(self, physical_board_fen, settings, virtual_board):
        exit_state = self.check_exit(physical_board_fen, type_='game')
        if physical_board_fen == virtual_board.fen():
            return exit_state, False

        # Do not update settings if last command happened recently
        if pygame.time.get_ticks() - self.last_command_time < self.wait_between_commands:
            return exit_state, False

        # Check if hint request
        hint_request = False
        if not settings['human_game']:
            temp_board = virtual_board.copy()
            temp_board.remove_piece_at(virtual_board.king(0))
            temp_board.remove_piece_at(virtual_board.king(1))
            if temp_board.board_fen() == physical_board_fen:
                logging.info('Remote control: Implicit hint request recognized')
                hint_request = True
                self.last_command_time = pygame.time.get_ticks() + 2000  # Wait five seconds until next hint request
        return exit_state, hint_request

    def thinking_window(self, physical_board_fen, virtual_board):
        '''
        Return true if one of the kings was removed from board. This will force move or hint during game loop
        '''

        # Do not update settings if last command happened recently
        if pygame.time.get_ticks() - self.last_command_time < self.wait_between_commands:
            return False

        # Check if force move
        for i in range(2):

            temp_board = virtual_board.copy()
            temp_board.remove_piece_at(virtual_board.king(i))
            if temp_board.board_fen() == physical_board_fen:
                logging.info('Remote control: Force move recognized')
                self.last_command_time = pygame.time.get_ticks()
                return True
        return False

    def check_exit(self, board_state, type_='application'):
        """
        Exit game by placing both kings in central squares.
        Flash all light for five seconds to indicate exit procedure
        """
        if not self.on:
            return 0

        if type_ == 'game':
            kings_in_exit_position = '/'.join(board_state.split('/')[3:5]).lower() in ('4k3/3k4', '3k4/4k3')
        else:
            kings_in_exit_position = '/'.join(board_state.split('/')[3:5]).lower() in ('4k3/4k3', '3k4/3k4')

        if pygame.time.get_ticks() - self.last_exit_command_time < self.wait_between_commands:
            if self.exit_command[type_]:
                # Check whether pieces were changed (option to abort)
                if kings_in_exit_position:
                    self.led_manager.flash_leds('all')
                else:
                    logging.info(f'Remote control: exit {type_} aborted')
                    self.led_manager.set_leds()
                    self.exit_command[type_] = False
                return 1  # In countdown to exit...

        if self.exit_command[type_]:
            self.exit_command[type_] = False
            return 2  # Exit!

        if kings_in_exit_position:
            logging.info(f'Remote control: exit {type_} initiated')
            self.exit_command[type_] = True
            self.last_exit_command_time = pygame.time.get_ticks() + (5000 - self.wait_between_commands)
            return 1

        return 0  # Not exiting.
