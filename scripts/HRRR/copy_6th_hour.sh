#!/usr/bin/env bash
# Script to copy previous 7th hour and make it the 6th for the following
#
# Example:
#   copy_6th_hour.sh hrrr.t09z.wrfsfcf07.grib2 hrrr.t10z.wrfsfcf06.grib2
#

set -e

# User input
SOURCE_FILE=$1
CREATED_FILE=$2

# Below should match the variables in the HRRR file, except for precipitation
HRRR_VARIABLES="HGT|TMP|RH|UGRD|VGRD|TCDC|DSWRF|VBDSF|VDDSF|DLWRF"
CREATED_HOUR=6

# Grab non-precip fields
wgrib2 ${SOURCE_FILE} \
  -match "${HRRR_VARIABLES}" \
  -set_date +1hr \
  -set_ftime "${CREATED_HOUR} hour fcst" \
  -grib_out ${CREATED_FILE}_1
# Instant precip for hour
wgrib2 ${SOURCE_FILE} \
  -match "APCP:surface:${CREATED_HOUR}-7 hour acc fcst" \
  -set_date +1hr \
  -set_ftime "5-${CREATED_HOUR} hour acc fcst" \
  -grib_out ${CREATED_FILE}_2

# Concatenate
cat ${CREATED_FILE}_{1,2} > ${CREATED_FILE}

# Remove tmp files
rm ${CREATED_FILE}_{1,2}

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

