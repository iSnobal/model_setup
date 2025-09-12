#!/bin/bash

#SBATCH --job-name=katana
#SBATCH --account=notchpeak-shared-short
#SBATCH --partition=notchpeak-shared-short

#SBATCH --time=6:00:00
#SBATCH --ntasks=24
#SBATCH --mem=14G

#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=umail@utah.edu

#SBATCH --chdir=/path/to/pwd
#SBATCH --output=slurm-%j.out-%N
#SBATCH --error=slurm-%j.err-%N

# Update the below use of conda according to the HPC docs
module load miniforge
mamba activate katana

START_YEAR=2019
START_MONTH=10

## Update these variables with the actual paths ##
INPUT_DIR=/path/to/HRRR
KATANA_OUTPUT_DIR=/path/to/katana/output/

KATANA_INI=/path/to/katana.ini
## -------------------------------------------- ##

for MONTH in {0..11}; do
  START=($(date -d "${START_MONTH}/01/${START_YEAR} + ${MONTH} month" "+%m %Y"))
  END=($(date -d "${START_MONTH}/01/${START_YEAR} + $((MONTH + 1)) month" "+%m %Y"))

  MONTH=${START[0]}
  YEAR=${START[1]}
  MONTH_END=${END[0]}
  YEAR_END=${END[1]}

  echo "Processing: ${YEAR}-${MONTH}"

  # Make copy to edit and have as backup
  MONTH_INI="${KATANA_OUTPUT_DIR}katana_${YEAR}${MONTH}.ini"
  cp ${KATANA_INI} ${MONTH_INI}

  # Update the config to the month processed
  sed -i -e "s/^start_date: .* UTC/start_date: ${YEAR}-${MONTH}-01 00:00:00 UTC/g" ${MONTH_INI}
  sed -i -e "s/^end_date: .* UTC/end_date: ${YEAR_END}-${MONTH_END}-01 00:00:00 UTC/g" ${MONTH_INI}
  # Update config file (line 17) and log path (line 22)
  sed -i -e "17s/katana_wn\.ini/katana_wn_${YEAR}${MONTH}\.ini/" ${MONTH_INI}
  sed -i -e "22s/katana\.log/katana_${YEAR}${MONTH}\.log/" ${MONTH_INI}

  # Run
  run_katana ${MONTH_INI} 1>&2

  if [ $? -ne 0 ]; then
    >&2 echo "ERROR processing ${YEAR}${MONTH}"
    continue
  fi
done

# Unused  katana output files by iSnobal
find ${KATANA_OUTPUT_DIR} -name *.prj -type f -delete
find ${KATANA_OUTPUT_DIR} -name *_cld.asc -type f -delete
## Unused temporary grib files created by katana
find ${KATANA_OUTPUT_DIR} -name *.grib2 -type f -delete
find ${KATANA_OUTPUT_DIR} -name hrrr.* -type d -empty -delete
