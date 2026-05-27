# Generate basin topo.nc for SMRF/iSnobal

Generates a `topo.nc` file containing DEM, basin mask, and vegetation layers
(type, height, tau, k) required to run SMRF/iSnobal. Vegetation defaults to
LANDFIRE 1.4.0; user-supplied rasters can also be substituted via `--veg-dir`.

No dependency on the USDA-ARS `basin_setup` repository.

## Requirements

- `basin_setup` conda environment (see `model_setup/conda/basin_setup.yaml`)
- Vegetation data — either LANDFIRE 1.4.0 or user-supplied input (see below)

## Vegetation data

Two options are supported:

### Option A — LANDFIRE 1.4.0 (default)

Download the **LF 1.4.0 EVT** and **LF 1.4.0 EVH** products for CONUS from
a *to-be-staged* repository and organize as follows:

```
<landfire-dir>/
  US_140EVT_20180618/
    Grid/us_140evt/hdr.adf
  US_140EVH_20180618/
    Grid/us_140evh/hdr.adf
    CSV_Data/LF_140EVH_05092014.csv
```

A veg params CSV mapping LANDFIRE EVT class IDs to SMRF canopy parameters (tau, k)
is also required. Pass its path with `--veg-params-csv`. In this approach, all 
vegetation parameters are categorical or discrete variables.

> **SnowHydRO group (UU CHPC):** all required datasets are currently staged at
> `/uufs/chpc.utah.edu/common/home/skiles-group3/LANDFIRE/`.

### Option B — user-supplied rasters (`--veg-dir`)

*** ***EXPERIMENTAL, TESTING REQUIRED*** ***  
If you have derived parameters, place the four 
required GeoTIFFs in a directory and pass in with `--veg-dir`:

```
<veg-dir>/
  veg_type.tif      # vegetation type class (categorical)
  veg_height.tif    # canopy height in metres (continuous)
  veg_tau.tif       # canopy transmissivity tau (continuous)
  veg_k.tif         # canopy extinction coefficient k (continuous)
```

All four files must cover the basin extent and be in a CRS that GDAL can reproject.
LANDFIRE is not required when using this option. Circumventing type and height is 
also possible (needed only in default generation of tau and k), but not yet tested.

## Quick start

```bash
$ cd model_setup
$ conda env create -f conda/basin_setup.yaml
$ conda activate basin_setup

$ cd scripts/topo

# View script options
$ python generate_topo.py -h
```

## Common invocation options
```bash
# Generate topo.nc using basin name, use quotes to handle spaces
$ python generate_topo.py -n "new fork" -o /path/to/output

# NB: multiple matches will print candidate basins in a table
# Select the correct hucid (or add specificity to basin name) and re-run
$ python generate_topo.py -n "gunnison" -o /path/to/output # this will yield 3 matches
    huc8                name  areasqkm states  
14020002      Upper Gunnison   6245.14     CO  
14020004 North Fork Gunnison   2509.66     CO  
14020005      Lower Gunnison   4306.26     CO  

# Re-run with more specificity
$ python generate_topo.py -n "lower gunnison" -o /path/to/output

# By HUC ID, defaults to HUC 8
$ python generate_topo.py -huc 14020005 -o /path/to/output

# From an existing UTM polygon file (GeoPackage)
$ python generate_topo.py -s /path/to/basin.gpkg -o /path/to/output

# With user-supplied vegetation rasters instead of LANDFIRE
$ python generate_topo.py -huc 14020005 -o /path/to/output --veg-dir /path/to/veg/
```

**Output:** `/path/to/output/output_<res>m/topo.nc`

## Scripts

| Script | Purpose |
|--------|---------|
| `generate_topo.py` | Orchestrates all three scripts |
| `fetch_basin.py` | Fetches HUC boundary from USGS WBD → UTM GeoPackage |
| `fetch_dem.py` | Streams or downloads 3DEP DEM tiles → warped GeoTIFF mosaic |
| `build_topo_nc.py` | Assembles polygon + DEM + vegetation → topo.nc |

Each script is independently runnable, provided that requisite data layers exist.

## Step-by-Step Examples

```bash
$ conda activate basin_setup

# Step 1: generate polygon and basin.env file by basin name
$ python fetch_basin.py -n "new fork" -o ./newfork_scripts

# [alternatively] fetch basin boundary by HUC ID
$ python fetch_basin.py -huc 14040102 -o ./newfork_scripts

# Step 2: mosaic DEM — streams via vsicurl by default (reads basin.env from step 1)
$ python fetch_dem.py -o ./newfork_scripts

# if tile download to disk is preferred, add flag, then warp
$ python fetch_dem.py -o ./newfork_scripts --download-tiles

# Step 3: build topo.nc using dem and vegetation (reads basin.env for paths)
# (LANDFIRE default)
$ python build_topo_nc.py -o ./newfork_scripts

# (user-supplied veg): bypass LANDFIRE with pre-derived rasters
$ python build_topo_nc.py -o ./newfork_scripts --veg-dir /path/to/veg/
```

Key output `basin.env` file is written by step 1 and appended in step 2, and contains:

```
BASIN_POLYGON="./newfork_scripts/huc14040102_basin.gpkg"
BASIN_EPSG="32612"
BASIN_BBOX="-110.0593,42.5219,-109.2101,43.2069"
BASIN_NAME="New Fork"
BASIN_DEM="./newfork_scripts/dem_epsg_32612_100m.tif"
```

## Options

```
generate_topo.py flags:
  -huc HUC_ID            HUC ID (e.g. 14050001)
  -n NAME                Basin name keyword (e.g. "Yampa")
  -s POLY                Existing UTM polygon file (shapefile or GeoPackage)
  -o DIR                 Output directory (required)
  -res METERS            Resolution in meters (default: 100)
  -level N               HUC level for -n search (default: 8)
  -e EPSG                Override auto-detected UTM EPSG
  --landfire-dir DIR     LANDFIRE 1.4.0 directory
  --veg-params-csv CSV   Veg params lookup CSV (used with --landfire-dir)
  --veg-dir DIR          User-supplied vegetation rasters, overrides --landfire-dir.
                         Must contain: veg_type.tif, veg_height.tif, veg_tau.tif, veg_k.tif
  --download-dem-tiles   Download DEM tiles to disk before warping (use for SLURM/offline)
  --skip-dem-download    Reuse existing tiles in <output>/dem_tiles/ (requires --download-dem-tiles)
```
