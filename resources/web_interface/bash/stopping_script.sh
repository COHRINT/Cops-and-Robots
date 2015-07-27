#!/bin/bash

# CGI script
setting=/var/www/html/optimized_web_interface/js/interface.js/setting
	# COLCRT=/usr/bin/colcrt

echo Content-type: text/plain
echo ""

# Determing which script to call
if [$setting == vicon]; then
	$setting_script = /bash/stop_vicon.sh
elif[$setting == gazebo]; then
	$setting_script = /bash/stop_gazebo.sh
elif [$setting == python]; then
	$setting_script = /bash/stop_python.sh
fi

# Port forwarding to 9222 and ssh into tyrell corp and run setting script
# ssh -L localport:host:hostport user@ssh_server -N 
ssh -L localport:192.168.20.110:9222 tyrell_corp@cohrint ./$setting_script