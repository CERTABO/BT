cd /home/pi/BT
sudo hciconfig hci0 piscan
sudo chmod 777 /var/run/sdp
python3 bluetooth_server.py
