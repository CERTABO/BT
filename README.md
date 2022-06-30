# BT
Bluetooth Server
# Instructions
CERTABO CHESS BOARD SOFTWARE

To install required libraries run:

    "python3 -m pip install -r requirements.txt"
    (or "pip3 pip install -r requirements.txt")

To launch application run:

    "python3 main.py --epaper"
"# Nano" 


    "sudo nano /etc/systemd/system/dbus-org.bluez.service"
    "add ‘-C’ at end of 'ExecStart' (ExecStart=/usr/lib/bluetooth/bluetoothd -C)"
    "add newline below (ExecStartPost=/usr/bin/sdptool add SP)"
    "sh bluetooth.sh"
