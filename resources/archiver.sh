#!/bin/bash
set -eu
install_file="/data/archiver.py"
if [[ ! -d "/data/" ]]; then
  mkdir /data/
fi
if [[ ! -e "$install_file" ]]; then
  curl -v -H "ApiUser: ${PTPAPI_APIUSER}" -H "ApiKey: ${PTPAPI_APIKEY}" "https://passthepopcorn.me/archive.php?action=script" \
       > "$install_file"
fi
/venv/bin/python ${install_file}  "$@" --config /data/config.ptp
