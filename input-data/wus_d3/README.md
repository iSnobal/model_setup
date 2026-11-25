# WUS-D3

Tools to prepare WUS-D3 data for SMRF input. These support the WUS-D3 hourly
files.

WUS-D3 is the Western US dynamically downscaled dataset. The data is publicly
available on [AWS S3](https://wrf-cmip6-noversioning.s3.amazonaws.com/index.html).

## Environment

```bash
conda env create -f wus_d3.yaml
conda activate wus_d3
```

## Grid metadata

SMRF needs the latitude, longitude and elevation of the WUS-D3 grid cells,
which the hourly files do not include. `wus_d3_metadata.py` creates a file
with this information. One file covers every basin in the WUS-D3 domain, so
it only needs to be created once.

```bash
python wus_d3_metadata.py -O WUS-D3_domain.nc
```

## How to use in SMRF

The metadata file covers the full WUS-D3 domain and only works with hourly
files that also cover the full domain. Do not crop the hourly files. SMRF
reads only the grid cells needed for the basin from them.

### SMRF `.ini` file

To use the data, set the following parameters in the `gridded` section:

```ini
...
[gridded]
data_type:           wrf
wrf_path:            /path/to/WUS-D3/hourly
wrf_prefix:          auxhist_d01
wrf_metadata:        /path/to/WUS-D3_domain.nc
...
```


## Tests

```bash
pytest test_wus_d3_metadata.py
```
