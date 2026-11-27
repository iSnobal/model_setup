# WUS-D3

Tools to prepare WUS-D3 data for SMRF input. These support the WUS-D3 hourly
files.

WUS-D3 is the Western US dynamically downscaled dataset. The data is publicly
available on [AWS S3](https://wrf-cmip6-noversioning.s3.amazonaws.com/index.html).
The available GCMs and scenarios are listed on the
[project page](https://atmos.ucla.edu/alexhall/cmip6-downscaling-using-wrf/),
and the dataset is described in
[Rahimi et al. (2024)](https://gmd.copernicus.org/articles/17/2265/2024/gmd-17-2265-2024.html)

## Environment

```bash
conda env create -f wus_d3.yaml
conda activate wus_d3
```

## Download

`wus_d3_download.py` downloads the hourly files of one GCM run for one water
year. September of the water year is not included, because WUS-D3 has data
from September to September. Only the variables SMRF needs are kept.

```bash
python wus_d3_download.py --gcm cesm2_r11i1p1f1 --scenario ssp370 --bias-corrected --water-year 2022 -O /path/to/WUS-D3
```

The files are saved in a folder named after the run, for example
`/path/to/WUS-D3/cesm2_r11i1p1f1_ssp370_bc`. Files that are already downloaded
are skipped, so an interrupted download continues when the same command is
run again. The available GCMs data are located in
[this bucket](https://wrf-cmip6-noversioning.s3.amazonaws.com/index.html#downscaled_products/gcm/).

## Grid metadata

SMRF needs the latitude, longitude and elevation of the WUS-D3 grid cells,
which the hourly files do not include. `wus_d3_metadata.py` creates a file
with this information. One file covers every basin in the WUS-D3 domain, so
it only needs to be created once.

```bash
python wus_d3_metadata.py -O WUS-D3_domain.nc
```

## How to use in SMRF

Set the file in the SMRF `.ini` file under the `gridded` section:

```ini
[gridded]
data_type:           wrf
wrf_path:            /path/to/WUS-D3/cesm2_r11i1p1f1_ssp370_bc
wrf_prefix:          auxhist_d01
wrf_metadata:        /path/to/WUS-D3_domain.nc
```

The metadata file covers the full WUS-D3 domain and only works with hourly
files that also cover the full domain. Do not crop the hourly files. SMRF
reads only the grid cells needed for the basin from them.

## Tests

```bash
pytest tests/
```
