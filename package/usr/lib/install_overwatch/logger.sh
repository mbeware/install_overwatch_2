#!/bin/bash
INSTALL_LOG="/var/log/install_overwatch.log"
CURL_LOG="/var/log/install_overwatch_curl_downloads.log"

mkdir -p /var/log
touch "$INSTALL_LOG" "$CURL_LOG"
chmod 666 "$INSTALL_LOG" "$CURL_LOG"

log_install() {
    echo "$(date --iso-8601=seconds) $1 command: $2" >> "$INSTALL_LOG"
}

log_curl() {
    echo "$(date --iso-8601=seconds) CURL command: curl $*" >> "$CURL_LOG"
}
