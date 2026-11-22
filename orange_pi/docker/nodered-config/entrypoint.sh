#!/bin/sh
set -eu

node /opt/gps/install-flows.js
cd /usr/src/node-red
exec npm start --cache /data/.npm -- --userDir /data --settings /opt/gps/settings.js
