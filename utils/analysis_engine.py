import logging
import os
import queue
import threading

import chess
import pygame

import cfg
from utils.get_books_engines import ENGINE_PATH
from utils.media import COLORS, show_text


class AnalysisObject:
    """
    Data Class that holds analysis status and results
    """

    def __init__(self, chessboard, root_moves=1):
        self.index = len(chessboard.move_stack)
        self.move = str(chessboard.move_stack[-1]) if self.index else ''  # To indentify move in case of take back
        self.turn = 1 - chessboard.turn if self.index else 1
        self.root_moves = 1
        self.data = None
        self.complete = False
        self.interrupted = False
        self.chessboard = chessboard.copy()
        self.default_value = 0

    def get_score(self):
        try:
            return int(self.data[0]['score'].white().score())
        except (TypeError, KeyError):  # Either data is still None or it returned None as a score
            return self.default_value

    def get_bestmove(self):
        try:
            return self.data[0]['pv'][0]
        except (TypeError, KeyError):
            return None


def analysis_thread(engine_settings, analysis_queue):
    """
    Analysis thread for game hint and evaluation

    It reads evaluation requests from main_to_thread and returns online results via thread_to_main.
    It automatically interrupts previous analysis if new one is requested  (it checks if this is the case every time
    the engine returns). In the case of interrupt it still sends the latest results.

    :param engine_path: dict (details with engine and settings)
    :param analysis_queue: queue ((index, python-chess chessboard object, number of branches to consider))
    """
    if not cfg.DEBUG_ANALYSIS:
        logging.getLogger('chess.engine').setLevel(logging.INFO)

    engine_path = os.path.join(ENGINE_PATH, engine_settings['engine'])
    if os.name == 'nt':
        engine_path += '.exe'

    engine = chess.engine.SimpleEngine.popen_uci(engine_path, debug=False)
    # Hack to allow setting of ponder
    try:
        chess.engine.MANAGED_OPTIONS.remove('ponder')
    except ValueError:
        pass

    for option, value in engine_settings.items():
        if option in ('engine', 'Depth'):
            continue
        if engine.options.get(option, None):
            engine.configure({option: value})
            if cfg.DEBUG_ANALYSIS:
                logging.info(f'Analysis: setting engine option {option}:{value}')
        else:
            if cfg.DEBUG_ANALYSIS:
                logging.info(f'Analysis: ignoring engine option {option}:{value}')

    depth = engine_settings['Depth']
    analysis = None
    analysis_request = None

    while True:
        # Check for new request
        try:
            # Block only if there is no current analysis being performed
            if analysis is None:
                new_analysis_request = analysis_queue.get()
            else:
                new_analysis_request = analysis_queue.get_nowait()
        except queue.Empty:
            pass
        # Process request
        else:
            if new_analysis_request is None:  # Quit
                if cfg.DEBUG_ANALYSIS:
                    logging.info('Analysis: Quitting analysis thread')
                engine.close()
                return

            # Deal with previous request
            if analysis is not None:
                analysis.stop()
                analysis_request.data = analysis.multipv
                analysis_request.interrupted = True
                if cfg.DEBUG_ANALYSIS:
                    logging.info(f'Analysis: Stopped previous request number {analysis_request.index}')

            # Ellipsis is used for interruption of analysis (but not killing of the engine)
            if new_analysis_request is ...:
                continue

            # Create new analysis from requset
            if cfg.DEBUG_ANALYSIS:
                logging.info(f'Analysis: Got new request number {new_analysis_request.index}')
            analysis_request = new_analysis_request
            request_board = analysis_request.chessboard
            request_root_moves = analysis_request.root_moves
            analysis = engine.analysis(request_board, multipv=request_root_moves, limit=chess.engine.Limit(depth=depth),
                                       info=chess.engine.Info.ALL)
            if cfg.DEBUG_ANALYSIS:
                logging.info(f'Analysis: Starting request number {analysis_request.index}')
                logging.info(f'Analysis result: {analysis_request.data}')

        # Block until next analysis update
        try:
            analysis.get()
            analysis_request.data = analysis.multipv
        except chess.engine.AnalysisComplete:
            analysis_request.data = analysis.multipv
            analysis_request.complete = True
            analysis = None
            if cfg.DEBUG_ANALYSIS:
                logging.info(f'Analysis: Request number {analysis_request.index} is done')
                logging.info(f'Final analysis data: {analysis_request.data}')


class Engine:
    """
    This base class interacts with engine threads, sending and reading analysis requests
    """

    def __init__(self, engine_settings):
        self.analysis_queue = queue.Queue()
        threading.Thread(target=analysis_thread, args=(engine_settings, self.analysis_queue), daemon=True).start()
        self.analysis_counter = 0
        self.analysis_history = {}
        self.history_limit = 1

    def request_analysis(self, chessboard, latest=True):
        analysis_object = AnalysisObject(chessboard)
        index = analysis_object.index
        self.analysis_history[index] = analysis_object
        self.analysis_queue.put(analysis_object)

        # Set default value to previous (if available)
        if latest:
            try:
                prev_analysis = self.analysis_history[index-1]
            except KeyError:
                pass
            else:
                analysis_object.default_value = prev_analysis.get_score()

        # Delete old keys
        if latest:
            self.analysis_counter = index
            delete_keys = [key for key in self.analysis_history.keys() if key < index - self.history_limit]
            for key in delete_keys:
                del self.analysis_history[key]

    def kill(self):
        self.analysis_queue.put(None)

    def interrupt(self):
        self.analysis_queue.put(...)


class GameEngine(Engine):
    """
    Extended Engine class with special methods to interrupt move and return best move
    """

    def __init__(self, engine_settings):
        super().__init__(engine_settings)
        self.lastfen = None
        self.bestmove = None

    def go(self, chessboard):
        """
        Request new moves and return if they are completed
        """
        # If new move is being requested
        if chessboard.fen() != self.lastfen:
            self.request_analysis(chessboard)
            self.lastfen = chessboard.fen()
            self.bestmove = None

    def waiting_bestmove(self):
        """
        Return True if analysis is completed, False otherwise
        """
        analysis = self.analysis_history[self.analysis_counter]
        self.bestmove = analysis.get_bestmove()

        if analysis.complete:
            return False
        else:
            return True

    def interrupt_bestmove(self):
        """
        Interrupt bestmove search provided at least one bestmove has been recorded
        :return:
        """
        self.waiting_bestmove()
        if self.bestmove is not None:
            self.interrupt()
            return True
        else:
            return False


class AnalysisEngine(Engine):
    """
    Extended Engine class with special methods to analyze multiple positions and plot the results
    """

    def __init__(self, engine_settings):
        super().__init__(engine_settings)
        self.history_limit = 9
        self.extended_analysis_completed = False
        self.plot = None

    def update_extended_analysis(self, chessboard):
        self.extended_analysis_completed = False
        current_index = len(chessboard.move_stack)

        # Delete newer keys (in case of take back)
        delete_keys = [key for key in self.analysis_history.keys() if key > current_index]
        if delete_keys:
            for key in delete_keys:
                del self.analysis_history[key]
            self.analysis_counter = max(self.analysis_history.keys())

        # Check if most recent analysis was launched already
        if current_index not in self.analysis_history:
            self.request_analysis(chessboard)
            return

        # If so, check if it is still ongoing
        if not self.analysis_history[current_index].complete:
            return

        # Check whether a previous analysis should be run
        board = chessboard.copy()
        for i in reversed(range(current_index)):
            # Limit retroactive analysis to history limit
            if current_index - i > self.history_limit:
                return

            board.pop()
            # If analysis was not launched, launch it
            if i not in self.analysis_history:
                self.request_analysis(board, latest=False)
                return

            analysis = self.analysis_history[i]
            # If analysis was interrupted, resume it
            if analysis.interrupted:
                analysis.interrupted = False
                self.analysis_queue.put(analysis)
                return

            # If analysis is still ongoing, return
            if not analysis.complete:
                return

        # Analysis is complete
        self.extended_analysis_completed = True

    @staticmethod
    def format_score(score):
        """
        Return '+score' for positive scores and '-score' for negative scores.
        Limit to 4 characters (add k if larger)
        """
        text_sign = '+' if score > 0 else ''

        if abs(score) < 10_000:
            text_score = f'{text_sign}{score}'
        else:
            score = score // 1000
            text_score = f'{text_sign}{score}k'

        return text_score

    def get_latest_score(self, return_incomplete=False):
        analysis = self.analysis_history[self.analysis_counter]
        if analysis.complete or return_incomplete:
            return f'{self.format_score(analysis.get_score())}(Cp)'
        else:
            return '   ...'

    def plot_extended_analysis(self, chessboard, clear_previous=False):
        """
        :param chessboard:
        :param clear_previous: Whether background needs to be cleared (used during inner AI loop)
        :return:
        """
        if self.plot is None:
            self.plot = AnalysisPlot(self.history_limit)
        self.update_extended_analysis(chessboard)
        self.plot.draw(self.analysis_history, self.analysis_counter, self.history_limit, self.extended_analysis_completed, clear_previous)


class AnalysisPlot:
    '''
    Takes care of plotting extended postion evaluation
    '''

    def __init__(self, history_limit):
        self.height = 35
        self.middle_y_coord_raw = 198
        self.start_y_coord_raw = self.middle_y_coord_raw - self.height
        self.end_y_coord_raw = self.middle_y_coord_raw + self.height

        self.start_x_coord_raw = 10
        self.end_x_coord_raw = 150

        self.middle_y_coord = int(self.middle_y_coord_raw * cfg.y_multiplier)
        self.start_y_coord = int(self.start_y_coord_raw * cfg.y_multiplier)
        self.end_y_coord = int(self.end_y_coord_raw * cfg.y_multiplier)
        self.start_x_coord = int(self.start_x_coord_raw * cfg.x_multiplier)
        self.end_x_coord = int(self.end_x_coord_raw * cfg.x_multiplier)
        self.x_step = (self.end_x_coord_raw - self.start_x_coord_raw + 10) / history_limit * cfg.x_multiplier

        self.marker_radius = int(2 * cfg.x_multiplier)
        self.label_min_y_distance = 5 * cfg.y_multiplier

        self.plot_area = pygame.Rect(
            self.start_x_coord - 5 * cfg.x_multiplier,
            self.start_y_coord - 3 * cfg.x_multiplier,
            self.end_x_coord - self.start_x_coord + 33 * cfg.x_multiplier,
            self.end_y_coord - self.start_y_coord + 14 * cfg.x_multiplier)

        self.plot_freeze = None

    def draw(self, analysis_history, analysis_counter, history_limit, extended_analysis_completed, clear_previous):
        # pygame.draw.rect(cfg.scr, COLORS['red'], self.plot_area)

        # Return frozen plot if nothing has changed, erase otherwise
        if not extended_analysis_completed:
            self.plot_freeze = None
        elif self.plot_freeze is not None:
            cfg.scr.blit(self.plot_freeze, self.plot_area)
            return

        # Erase plot area
        if clear_previous:
            pygame.draw.rect(cfg.scr, COLORS['white'], self.plot_area)

        # Get scores and colors
        scores, colors, moves = [], [], []
        current_index = analysis_counter
        start_index = current_index - history_limit + 1
        for index in range(max(0, start_index), current_index + 1):
            try:
                analysis_object = analysis_history[index]
                scores.append(analysis_object.get_score())
                moves.append(analysis_object.move)
                color = COLORS['grey'] if analysis_object.turn else COLORS['black']
                colors.append(color)
            except KeyError:
                scores.append(0)
                moves.append('')
                colors.append(COLORS['white'])
        colors[-1] = COLORS['niceblue']

        # Define coordinates
        min_score = min(scores)
        max_score = max(scores)
        range_normalizer = max(abs(min_score), abs(max_score), 1) / (self.height - 2)
        points = []
        for i, score in enumerate(scores, 0):
            x_coord = int(self.start_x_coord + 5 + i * self.x_step)
            y_coord = int(self.middle_y_coord - score / range_normalizer * cfg.y_multiplier)
            points.append((x_coord, y_coord))

        # Draw background
        pygame.draw.rect(cfg.scr, COLORS['lightestgrey2'],
                         pygame.Rect(self.start_x_coord, self.start_y_coord,
                                     self.end_x_coord - self.start_x_coord,
                                     self.middle_y_coord - self.start_y_coord))
        pygame.draw.rect(cfg.scr, COLORS['lightestgrey'],
                         pygame.Rect(self.start_x_coord, self.middle_y_coord,
                                     self.end_x_coord - self.start_x_coord,
                                     self.middle_y_coord - self.start_y_coord))

        # Draw graph lines
        if len(points) > 1:
            pygame.draw.aalines(cfg.scr, COLORS['black'], False, points)

        # Draw guiding lines
        min_score_y = points[scores.index(min_score)][1]
        max_score_y = points[scores.index(max_score)][1]
        pygame.draw.line(cfg.scr, COLORS['lightgrey'], (self.start_x_coord, min_score_y), (self.end_x_coord, min_score_y), 1)
        pygame.draw.line(cfg.scr, COLORS['lightgrey'], (self.start_x_coord, max_score_y), (self.end_x_coord, max_score_y), 1)
        pygame.draw.line(cfg.scr, COLORS['niceblue'], (self.start_x_coord, points[-1][1]), (self.end_x_coord, points[-1][1]), 1)

        # Draw points
        for point, color in zip(points, colors):
            pygame.draw.circle(cfg.scr, color, point, self.marker_radius)

        # Yaxis ticks
        show_text(AnalysisEngine.format_score(scores[-1]), self.end_x_coord_raw + 2, points[-1][1] / cfg.y_multiplier, COLORS['niceblue'], fontsize='small',
                  centerY=True)
        # Only show other ticks if they are not too close to latest
        if abs(min_score_y - points[-1][1]) > self.label_min_y_distance:
            show_text(AnalysisEngine.format_score(min_score), self.end_x_coord_raw + 2, min_score_y / cfg.y_multiplier, COLORS['grey'], fontsize='small',
                      centerY=True)
        if abs(max_score_y - points[-1][1]) > self.label_min_y_distance:
            show_text(AnalysisEngine.format_score(max_score), self.end_x_coord_raw + 2, max_score_y / cfg.y_multiplier, COLORS['grey'], fontsize='small',
                      centerY=True)

        # Xaxis ticks
        if cfg.xresolution != 480:
            for move, color, point in zip(moves, colors, points):
                # Ticks
                pygame.draw.line(cfg.scr, COLORS['black'], (point[0], self.end_y_coord - 1 * cfg.y_multiplier),
                                 (point[0], self.end_y_coord + 1 * cfg.y_multiplier))
                # Labels
                show_text(move, point[0] / cfg.x_multiplier, self.end_y_coord_raw + 5,
                          color, fontsize='verysmall', centerX=True, centerY=True)
        else:
            for move, color, point in zip(moves[::-2], colors[::-2], points[::-2]):
                # Ticks
                pygame.draw.line(cfg.scr, COLORS['black'], (point[0], self.end_y_coord - 2 * cfg.y_multiplier),
                                 (point[0], self.end_y_coord + .5 * cfg.y_multiplier))
                # Labels
                show_text(move, point[0] / cfg.x_multiplier, self.end_y_coord_raw + 5,
                          color, fontsize='small', centerX=True, centerY=True)

        # Freeze plot if its complete
        if extended_analysis_completed:
            self.plot_freeze = cfg.scr.subsurface(self.plot_area).copy()

