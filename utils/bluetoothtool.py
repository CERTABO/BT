import logging
import multiprocessing
import queue
import select
import threading
import time

import bluetooth

import cfg
from utils import usbtool


def _bluetothtool(address_chessboard, queue_to_usbtool, queue_from_usbtool):
    logging.info("--- Starting Bluetoothtool ---")

    socket = None
    socket_ok = False
    first_connection = True

    while True:
        time.sleep(.001)

        # Try to (re)connect to board
        if not socket_ok:
            try:
                if not first_connection:
                    socket.close()
                    address_chessboard = find_address() if cfg.args.btport is None else cfg.args.btport
                    if address_chessboard is None:
                        time.sleep(.5)
                        continue

                socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                socket.connect((address_chessboard, cfg.BTPORT))

            except Exception as e:
                logging.warning(f'Failed to (re)connect to port {address_chessboard}: {e}')
                time.sleep(1)
                continue

            else:
                socket_ok = True
                socket_list = [socket]
                if first_connection:
                    first_connection = False

        # Write led info
        try:
            new_message = queue_to_usbtool.get_nowait()
            socket.send(new_message)
        except queue.Empty:
            pass
        except bluetooth.btcommon.BluetoothError as e:
            print("Lost connection to device:", e)
            socket_ok = False
            continue

        # Read board info
        readable, _, _ = select.select(socket_list, [], [], 0)
        if readable:
            try:
                data = socket.recv(1024).decode('utf-8')
                # If no data, port is probably closed
                if not data:
                    print('Lost connection to device: no data')
                    socket_ok = False
                    continue
                queue_from_usbtool.put(data)
            except bluetooth.btcommon.BluetoothError as e:
                print("Lost connection to device:", e)
                socket_ok = False


def start_bluetoothtool(address_chessboard, separate_process=False):

    if separate_process:
        logging.info('Launching BluetoothTool in separate process')
        usbtool.QUEUE_FROM_USBTOOL = multiprocessing.Queue()
        usbtool.QUEUE_TO_USBTOOL = multiprocessing.Queue()
        process = multiprocessing.Process(target=_bluetothtool,
                                          args=(address_chessboard, usbtool.QUEUE_TO_USBTOOL, usbtool.QUEUE_FROM_USBTOOL),
                                          daemon=True)
        process.start()
        return process

    else:
        logging.info('Launching BluetoothTool in separate thread')
        thread = threading.Thread(target=_bluetothtool,
                                  args=(address_chessboard, usbtool.QUEUE_TO_USBTOOL, usbtool.QUEUE_FROM_USBTOOL),
                                  daemon=True)
        thread.start()
        return thread


def find_address(test_address=None):
    """
    Method to find Certabo Chess Bluetooth address.

    It looks for BT devices who may be listening on port 10.
    TODO: Use BT service when fixed on Windows.

    If test_address: it tries to find and connect only to the given address.
    """

    logging.info(f'test_address: {test_address}')
    btaddress = test_address
    failed_addresses = set()
    while True:

        while btaddress is None:
            logging.info('Looking for new Bluetooth devices')
            # logging.info(f'Looking for Certabo bluetooth service with address: {btaddress}')

            try:
                devices = bluetooth.discover_devices()
            except OSError:
                logging.warning('Bluetooth adapter not available, make sure computer bluetooth system is turned on.')
                return None
                # raise NoBluetoothAdapterFound
            # services = bluetooth.find_service(uuid="41c9ee4d-871e-4556-b521-84c89c24710a", name='Certabo', address=btaddress)

            if not devices:
                logging.info('Did not find any Bluetooth device. Make sure RaspberryPi is connected to Computer through Bluetooth and that the Certabo bluetooth_server.py is running on the RaspberryPi.')
                return None
            else:
                for address in devices:
                    # Ignore different addresses when testing specific address
                    if (test_address is not None) and (test_address != address):
                        continue
                    if address not in failed_addresses:
                        btaddress = address
                        logging.info(f'Found candidate device: {btaddress}')
                        break
                else:  # nobreak: tried all devices
                    logging.info('Did not find any Bluetooth device. Make sure RaspberryPi is connected to Computer through Bluetooth and that the Certabo bluetooth_server.py is running on the RaspberryPi.')
                    return None

        logging.info(f'Connecting to address {btaddress}, {cfg.BTPORT}.')
        socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        try:
            socket.connect((btaddress, cfg.BTPORT))
        except OSError:
            logging.info(f'Failed to connect.')
            if test_address is not None:
                return None
            failed_addresses.add(btaddress)
            btaddress = None
            continue

        logging.info('Connected successfully, returing address.')
        socket.close()
        return btaddress


class NoBluetoothAdapterFound(Exception):
    pass
