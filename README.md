# BT
Bluetooth Server
Instructions
sudo nano /etc/systemd/system/dbus-org.bluez.service
add ‘-C’ at end of 'ExecStart' (ExecStart=/usr/lib/bluetooth/bluetoothd -C)
add newline below (ExecStartPost=/usr/bin/sdptool add SP)
sh bluetooth.sh
