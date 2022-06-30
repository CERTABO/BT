# BT
Bluetooth Server
# Instructions
CERTABO CHESS BOARD SOFTWARE

To install required libraries run:

    "sudo apt-get install bluez python-bluez"
    (or "sudo python3 -m pip install pybluez")
    "you may also need sudo apt-get install bluetooth bluez libbluetooth-dev"
#To launch BT Server
    "sudo nano /etc/systemd/system/dbus-org.bluez.service"
    "add ‘-C’ at end of 'ExecStart' (ExecStart=/usr/lib/bluetooth/bluetoothd -C)"
    "add newline below (ExecStartPost=/usr/bin/sdptool add SP)"
    "sh bluetooth.sh"
