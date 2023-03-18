#!/bin/bash
set -u
archive_script="/data/archiver.py"
if [[ ! -d "/data/" ]]; then
  mkdir /data/
fi
cd /data/ || exit 1 # Exit if /data/ isn't available
if [[ ! -e "$archive_script" ]]; then
  echo "archiver.py does not exist, installing"
  wget --header "ApiUser: ${PTPAPI_APIUSER}" --header "ApiKey: ${PTPAPI_APIKEY}" \
       "https://passthepopcorn.me/archive.php?action=script"  \
       -O "$archive_script"
  if [ $? -ne 0 ] ; then
    echo "Could not download script"
    if [[ -e "$archive_script" ]]; then
      cat "$archive_script"
      rm -f "$archive_script"
    fi
    exit
  fi
fi
/venv/bin/python "${archive_script}"  "$@"
