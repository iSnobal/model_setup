# iSnobal Topo File Updating Scripts

This folder contains R Markdown workflows for updating the `topo.nc` model domain metadata file.

## Available Scripts

### Vegetation Parameters Using LANDFIRE
- [LFUpdate2Topo_PostFireRun.Rmd](LFUpdate2Topo_PostFire.Rmd)

### Vegetation Parameters Using MTBS Burn Severity
- [MTBSUpdate2Topo_BurnSeverityRun.Rmd](MTBSUpdate2Topo_BurnSeverity.Rmd)

Both scripts are intended to be run in [**RStudio**](https://posit.co/products/open-source/rstudio.

---

# Requirements

Before running the scripts, install the following:

- [R](https://www.r-project.org/)
- [RStudio](https://posit.co/download/rstudio-desktop/)

You will also need to install several R packages.

Ensure to run the following command in RStudio before running any of the scripts:

```r
install.packages(c("tidyverse", "sf", "terra", "raster", "ncdf4"))
```

Once packages are installed and file paths are configured, the scripts can be executed using 
the instructions below.

---

# Scripts
## `LFUpdate2Topo_PostFire.Rmd` Instructions

### 1. Download LANDFIRE Products

Download the following products for your basin:

- Existing Vegetation Type (EVT)
- Existing Vegetation Height (EVH)

Use the LANDFIRE Map Viewer download tool:

https://www.landfire.gov/viewer/

#### Important Notes

##### Projection
Make sure the downloaded data uses the **same projection** as your original `topo.nc` file.

##### Version Selection
Choose the appropriate LANDFIRE version for your study area and timeframe using the comparison table:

https://www.landfire.gov/data/comparison-table

### 2. Extract Raster Files

Extract only the `.TIF` files from both:

- EVT
- EVH

These raster files will be loaded directly by the update script.

### 3. Back Up Your Original topo.nc File

:warning: **Important**  
The script edits the `topo.nc` file directly.

Before running the script:

- Create a copy of your original `topo.nc`
- Keep the original stored separately as a backup

### 4. Download Parameter CSV

Download:

- `landfire_veg_params_updated.csv`

This file is used to populate the vegetation `k` and `tau` values.

### 5. Run the Script

After configuring file paths:

- Run the R Markdown script in RStudio
- Verify raster orientation and alignment with your study area
- Confirm that:
  - DEM orientation is correct
  - `k` and `tau` values are within expected ranges

## `MTBSUpdate2Topo_BurnSeverity.Rmd` Instructions

The same workflow as the above applies to:

- [MTBSUpdate2Topo_BurnSeverity.Rmd](MTBSUpdate2Topo_BurnSeverity.Rmd)

Instead of LANDFIRE products, download:

- MTBS Thematic Burn Severity Classes

Available from the MTBS Direct Download Portal:

https://burnseverity.cr.usgs.gov/direct-download

---

# General Notes

- Ensure all datasets use matching coordinate systems and extents.
- Carefully inspect outputs before replacing operational topo files.

---

Author: [Hellen Flynn](https://github.com/helenflynnn)
