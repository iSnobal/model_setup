#!/usr/bin/env bash
# Download HRRR data
#
# Can either be given two arguments for year and month:
#   ./download_hrrr.sh YYYY MM (Archive)
# a range of dates to loop through given as one comma-separated argument:
#   ./download_hrrr.sh YYYYMMDD,YYYYMMDD (Archive)
# or a single date:
#   ./download_hrrr.sh YYYYMMDD (Archive)
#
# The third is optional and can specify the archive source. Default
# is to get from Google and can be changed to the University of Utah
# by passing 'UofU', Amazon with 'AWS', or Microsoft with 'Azure'.
# Invalid date or archive inputs will be rejected and the script will exit.

# Colorado Basin River bounding box from:
# https://www.sciencebase.gov/catalog/item/4f4e4a38e4b07f02db61cebb
#
# List days after a download, where there are not 48 files for a day:
# find -L . -name *.grib2 -type f | cut -d/ -f2 | uniq -c | grep -v '48 ' | tr -s ' ' | cut -d '.' -f 2
#
set -e

export HRRR_VARS='TMP:2 m|RH:2 m|DPT:2 m|UGRD:10 m|VGRD:10 m|TCDC:|APCP:surface|DSWRF:surface|DLWRF:surface|VBDSF:surface|VDDSF:surface|HGT:surface'
export HRRR_FC_HOURS=(1 6)
export HRRR_DAY_HOURS=({0..23})

# Western United States from Denver West
export GRIB_AREA="-122.00:-105.00 32.00:49.00"
# Job control - the defaults require to have 32 CPUs for the job
## Number of jobs to download in parallel
PARALLEL_JOBS=16
## Number of Grib threads
export GRIB_THREADS="-ncpu 2"
## Control when checking file presence
export SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export EXIT_ON_SUCCESS="true"

# When adding a new archive, update ARCHIVE_NAMES and add ARCHIVE_URL_{NAME}
# with the url template. DAY and FILE are substituted in set_archive_url().
export ARCHIVE_NAMES="UofU AWS Google Azure"
export DEFAULT_ARCHIVE="Google"
export ARCHIVE_URL_UofU="https://pando-rgw01.chpc.utah.edu/hrrr/sfc/DAY/FILE"
export ARCHIVE_URL_AWS="https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.DAY/conus/FILE"
export ARCHIVE_URL_Google="https://storage.googleapis.com/high-resolution-rapid-refresh/hrrr.DAY/conus/FILE"
export ARCHIVE_URL_Azure="https://noaahrrr.blob.core.windows.net/hrrr/hrrr.DAY/conus/FILE"

check_valid_date() {
  if ! date -d "$1" "+%Y%m%d" > /dev/null 2>&1; then
    echo "Invalid date detected, ensure input is valid and follows format YYYYMMDD: $1"
    exit 1
  elif [[ $(date -d "$1" "+%Y%m%d") -gt $(date "+%Y%m%d") ]]; then
    echo "Invalid date: $1 is in the future."
    exit 1
  fi
}

set_archive_url() {
  # Rely on ARCHIVE_NAME to identify correct URL template var
  local day="${ALT_DATE:-$DATE}"
  local var="ARCHIVE_URL_$1"
  local template="${!var}"
  if [[ -z "$template" ]]; then
    >&2 printf "Unknown archive: %s\n" "$1"
    return 1
  fi
  # Substitute DAY and FILE with actual values to get correct URL
  export ARCHIVE_URL="${template/DAY/$day}"
  ARCHIVE_URL="${ARCHIVE_URL/FILE/$FILE_NAME}"
}
export -f set_archive_url

check_file_in_archive() {
  set_archive_url "$1"
  STATUS_CODE=$(curl -s -o /dev/null -I -w "%{http_code}" "${ARCHIVE_URL}")

  if [ "${STATUS_CODE}" == "404" ]; then
    >&2 printf "   missing\n"
    return 3
  fi

  >&2 printf "\n"
  unset ALT_DATE
  return 0
}
export -f check_file_in_archive

check_alternate_archive() {
    local var="ARCHIVE_URL_$1"
    local archives
    if [[ -n "${!var}" ]]; then
      archives=("$1")
      >&2 printf "  Input detected: %s\n" "$1"
    else
      read -ra archives <<< "$ARCHIVE_NAMES"
    fi

    >&2 printf "  Checking alternate archive: \n"
    for ALT_ARCHIVE in "${archives[@]}"; do
      if [[ "${ALT_ARCHIVE}" == "${ARCHIVE}" ]]; then
        continue
      fi

      >&2 printf "   - %s" "${ALT_ARCHIVE}"
      check_file_in_archive "${ALT_ARCHIVE}"
      if [ $? -eq 0 ]; then
        return 0
      fi
    done

    unset ALT_DATE
    touch "${FILE_NAME}.missing"
    return 3
}
export -f check_alternate_archive

check_file_existence(){
  # Check for existing nonzero file on disk
  # Pass EXIT_ON_SUCCESS to exit the job when found.
  # return 3 on failure and signal alt pathway
  if [[ -s "${FILE_NAME}" ]]; then
    if [[ "${1}" == "${EXIT_ON_SUCCESS}" ]]; then
      printf "  exists \n"
      exit 0
    fi
    return 0
  fi
  return 3
}
export -f check_file_existence

get_grib_range(){
  INDEX_FILE=$(curl -s "${ARCHIVE_URL}.idx")
  RANGE_GREP="grep -A 1 -B 1 "

  export MIN_RANGE=$(echo "${INDEX_FILE}" | ${RANGE_GREP} -E "${HRRR_VARS}" | cut -d ":" -f 2 | head -n 1)
  export MAX_RANGE=$(echo "${INDEX_FILE}" | ${RANGE_GREP} -E "${HRRR_VARS}" | cut -d ":" -f 2 | tail -n 1)
}
export -f get_grib_range

download_hrrr() {
  DAY_HOUR=$1
  FC_HOUR=$2
  FILE_NAME="hrrr.t$(printf "%02d" $DAY_HOUR)z.wrfsfcf0${FC_HOUR}.grib2"
  MISSING_FILE=""

  printf "File: ${FILE_NAME} \n"

  # Clean up any old temporary pipes from previous runs
  find . -type p -name "${FILE_NAME}_tmp" -delete
  # Remove any previous downloads of empty grib files
  find . -type f -name "${FILE_NAME}" -size 0 -delete
  # Remove any previously missing files in archives and try again
  find . -type f -name "${FILE_NAME}.missing" -size 0 -delete

  check_file_existence ${EXIT_ON_SUCCESS}

  check_file_in_archive "${ARCHIVE}"

  if [[ $? -eq 3 ]]; then
    check_alternate_archive
  fi

  if [[ $? -eq 3 ]]; then
    >&2 printf "  ** Forecast hour ${FC_HOUR} not available **\n"

    # Try a previous hour of the day if either F01 or F06 is missing
    if [[ ${FC_HOUR} -eq 1 ]] || [[ ${FC_HOUR} -eq 6 ]]; then
      MISSING_FILE="$FILE_NAME"
      if [[ ${FC_HOUR} -eq 1 ]]; then
        COPY_SCRIPT="$SCRIPT_DIR/copy_1st_hour.sh"
      else
        COPY_SCRIPT="$SCRIPT_DIR/copy_6th_hour.sh"
      fi
      NEW_DATE=$(date -u -d "${DATE} $(printf "%02d" $DAY_HOUR):00:00 1 hour ago" "+%Y%m%d%H")
      ALT_DATE=${NEW_DATE:0:-2}
      FILE_NAME="hrrr.t${NEW_DATE:(-2)}z.wrfsfcf0$(($FC_HOUR + 1)).grib2"

      >&2 printf "  ** Checking previous hour: hrrr.${ALT_DATE}/${FILE_NAME}"

      if [[ "${ALT_DATE}" == "${DATE}" ]] && check_file_existence; then
        >&2 printf "  surrogate file exists on disk, copying now...\n"
        "$COPY_SCRIPT" "$FILE_NAME" "$MISSING_FILE"
        exit 0
      fi

      check_file_in_archive "${ARCHIVE}"

      if [[ $? -eq 3 ]]; then
        check_alternate_archive

        if [[ $? -eq 3 ]]; then
          >&2 printf "  not available in previous hour\n"
          # Safe for parallel jobs: single short filenames
          echo "$MISSING_FILE" >> "../missing_HRRR_files_${DATE}.log"
          exit 0
        fi
      else
        >&2 printf "   found previous hour\n"
      fi
    else
      exit 0
    fi
  fi

  TMP_FILE="${FILE_NAME}_tmp"
  mkfifo "$TMP_FILE"

  # Reduce download size of GRIB file by requesting a specific range
  get_grib_range

  printf '\n'
  curl -s --range "${MIN_RANGE}-${MAX_RANGE}" "${ARCHIVE_URL}" -o "$TMP_FILE" | \
  wgrib2 "$TMP_FILE" -v0 ${GRIB_THREADS} -set_grib_type same -small_grib ${GRIB_AREA} - | \
  wgrib2 - -v0 ${GRIB_THREADS} -match "${HRRR_VARS}" -grib "$FILE_NAME"

  rm "$TMP_FILE"

  # If download produced zero size file, retry with alternate archives
  if [[ ! -s "$FILE_NAME" ]]; then
    >&2 printf "  File is zero size, checking alternate archives...\n"

    # Loop through alternate archives until file is no longer zero size
    # or all archives have been checked.
    for ALT_ARCHIVE in $ARCHIVE_NAMES; do
      if [[ "${ALT_ARCHIVE}" == "${ARCHIVE}" ]]; then
        continue
      fi
      check_file_in_archive "$ALT_ARCHIVE"
      if [[ $? -eq 0 ]]; then
        get_grib_range
        mkfifo "$TMP_FILE"
        curl -s --range "${MIN_RANGE}-${MAX_RANGE}" "${ARCHIVE_URL}" -o "$TMP_FILE" | \
        wgrib2 "$TMP_FILE" -v0 ${GRIB_THREADS} -set_grib_type same -small_grib ${GRIB_AREA} - | \
        wgrib2 - -v0 ${GRIB_THREADS} -match "${HRRR_VARS}" -grib "$FILE_NAME" >&1
        find . -type f -name "${FILE_NAME}.missing" -size 0 -delete
        rm "$TMP_FILE"
        # break loop once file successfully downloaded and nonzero
        [[ -s "$FILE_NAME" ]] && break
        # Otherwise keep going
        >&2 printf "  Still zero size from %s\n" "$ALT_ARCHIVE"
      fi
    done
  fi

  if [[ -s "$FILE_NAME" ]]; then
    # Create index file
    wgrib2 -s "${FILE_NAME}" > "${FILE_NAME}.idx"
    printf " created \n"
  fi

  # If the previous hour forecast successfully downloaded, replace missing file with it
  if [[ -n "$MISSING_FILE" ]] && [[ -s "$FILE_NAME" ]]; then
    "$COPY_SCRIPT" "$FILE_NAME" "$MISSING_FILE"
  fi
}
export -f download_hrrr

# ── Main ──────────────────────────────────────────────────────────────────────
# Parse the given user inputs for dates
if [[ $1 =~ ^[0-9]{4}$ ]] && [[ $2 =~ ^[0-9]{1,2}$ ]]; then
  # Regex pattern to match YYYY MM
  YEAR=$1
  MONTH=$(printf "%02d" "$((10#${2}))")
  LAST_DAY=$(date -d "${MONTH}/01/${YEAR} + 1 month - 1 day" +%d)
  check_valid_date ${YEAR}${MONTH}${LAST_DAY}

  export DATES=($(seq -f "${YEAR}${MONTH}%02g" 1 $LAST_DAY))
elif [[ $1 =~ ^([0-9]{8}),([0-9]{8})$ ]]; then
  # Regex pattern to match YYYYMMDD,YYYYMMDD
  START_DATE="${BASH_REMATCH[1]}"
  END_DATE="${BASH_REMATCH[2]}"
  check_valid_date "$START_DATE"
  check_valid_date "$END_DATE"

  if [[ "$START_DATE" -gt "$END_DATE" ]]; then
    echo "Invalid range: start date must be <= end date"
    exit 1
  fi

  DATES=()
  CURRENT_DATE="$START_DATE"
  while [[ "$CURRENT_DATE" -le "$END_DATE" ]]; do
    DATES+=("$CURRENT_DATE")
    CURRENT_DATE=$(date -d "${CURRENT_DATE:0:4}-${CURRENT_DATE:4:2}-${CURRENT_DATE:6:2} + 1 day" +%Y%m%d)
  done
  export DATES
elif [[ $1 =~ ^[0-9]{8}$ ]]; then
  # Regex pattern to match single YYYYMMDD
  check_valid_date "$1"
  export DATES=("$1")
else
  echo "Invalid input. Use either: YYYY MM [Archive] OR YYYYMMDD,YYYYMMDD [Archive] OR YYYYMMDD [Archive]"
  exit 1
fi

# Set the archive ($3 for YYYY MM mode, $2 for date-range or single date mode)
ARCHIVE_ARG="${3:-$2}"
# Check if ARCHIVE_ARG is empty
if [[ -z "$ARCHIVE_ARG" ]]; then
  export ARCHIVE="$DEFAULT_ARCHIVE"
# Check if input is valid, spacing ensures input matches an archive option
elif [[ " $ARCHIVE_NAMES " == *" $ARCHIVE_ARG "* ]]; then
  export ARCHIVE="$ARCHIVE_ARG"
else
  echo "Invalid archive specified: $ARCHIVE_ARG. Valid options are: $ARCHIVE_NAMES."
  exit 1
fi
unset ARCHIVE_ARG

printf "Getting files from: ${ARCHIVE}\n"

# Get the data
for DATE in "${DATES[@]}"; do
  printf "Processing: $DATE\n"
  export DATE=${DATE}

  FOLDER="hrrr.${DATE}"
  mkdir -p "$FOLDER"
  pushd "$FOLDER" > /dev/null

  parallel --tag --line-buffer --jobs ${PARALLEL_JOBS} download_hrrr ::: "${HRRR_DAY_HOURS[@]}" ::: "${HRRR_FC_HOURS[@]}"

  popd > /dev/null
done
