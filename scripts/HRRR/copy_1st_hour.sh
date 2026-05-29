#!/usr/bin/env bash
# Script to copy previous 2nd hour and make it the 1st for the following
#
# Example:
#   copy_1st_hour.sh hrrr.t09z.wrfsfcf02.grib2 hrrr.t10z.wrfsfcf01.grib2
#

set -e

SOURCE_FILE=$1
CREATED_FILE=$2

# Below should match the variables in the HRRR file, except for precipitation
HRRR_VARIABLES="HGT|TMP|RH|UGRD|VGRD|TCDC|DSWRF|VBDSF|VDDSF|DLWRF|APCP:surface:1-2 hour"
CREATED_HOUR=1

# Adjust datetime stamp and forecast time
wgrib2 ${SOURCE_FILE} \
  -match "${HRRR_VARIABLES}" \
  -set_date +1hr \
  -set_ftime "${CREATED_HOUR} hour fcst" \
  -grib_out ${CREATED_FILE}

# Print to verify output
echo " ** Result **"
wgrib2 -v2 ${CREATED_FILE}

echo " ** Creating index file for ${CREATED_FILE} **"
# Create index file for created file
wgrib2 -s ${CREATED_FILE} > ${CREATED_FILE}.idx

# Clean up missing file
find . -type f -name "${CREATED_FILE}.missing" -size 0 -delete

# Remove SOURCE_FILE and its index file
rm ${SOURCE_FILE} ${SOURCE_FILE}.idx

