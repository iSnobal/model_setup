#!/usr/bin/env python
"""
Build a topo.nc file for SMRF/iSnobal from a basin polygon file, a warped DEM
GeoTIFF, and vegetation data (LANDFIRE 1.4.0 or user-supplied via --veg-dir).

Writes output/topo.nc and validates its CRS against the expected EPSG.

Usage:
    python build_topo_nc.py -o ./newfork_scripts           # reads basin.env
    python build_topo_nc.py -s custom_basin.gpkg -d custom_dem.tif -o /path/to/outputs/
    python build_topo_nc.py -o ./newfork_scripts --veg-dir /path/to/veg/
"""

import argparse
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
import xarray as xr
from osgeo import gdal
from pyproj import CRS
from rasterio.features import rasterize

LANDFIRE_DIR_DEFAULT = Path("/uufs/chpc.utah.edu/common/home/skiles-group3/LANDFIRE")
VEG_PARAMS_CSV_DEFAULT = LANDFIRE_DIR_DEFAULT / "landfire_veg_params_assigned.csv"

# Relative paths within the LANDFIRE 1.4.0 directory
_EVT_PATH = "US_140EVT_20180618/Grid/us_140evt/hdr.adf"
_EVH_PATH = "US_140EVH_20180618/Grid/us_140evh/hdr.adf"
_EVH_CSV = "US_140EVH_20180618/CSV_Data/LF_140EVH_05092014.csv"

# Contract for user-supplied vegetation rasters via --veg-dir.
# veg_type is categorical so uses nearest-neighbour resampling; others are continuous.
VEG_DIR_FILES = {
    "veg_type":   ("veg_type.tif",   "near"),
    "veg_height": ("veg_height.tif", "bilinear"),
    "veg_tau":    ("veg_tau.tif",    "bilinear"),
    "veg_k":      ("veg_k.tif",      "bilinear"),
}

# Matches numeric height values in CLASSNAMES strings, excluding asterisk-delimited NoData markers
_HEIGHT_RE = re.compile(r"(?<!\*)(\d*\.?\d+)(?!\*)")


def _padded_extents(polygon, cell_size, pad_cells=5):
    """Return [xmin, ymin, xmax, ymax] in polygon CRS, padded and cell-aligned."""
    gdf = gpd.read_file(polygon)
    xmin, ymin, xmax, ymax = gdf.total_bounds
    pad = cell_size * pad_cells
    # Align to cell grid so all rasters share a common pixel origin
    xmin = math.floor((xmin - pad) / cell_size) * cell_size
    ymin = math.floor((ymin - pad) / cell_size) * cell_size
    xmax = math.ceil((xmax + pad) / cell_size) * cell_size
    ymax = math.ceil((ymax + pad) / cell_size) * cell_size
    return [xmin, ymin, xmax, ymax], gdf.crs.srs


def _clip_raster(src, dst, crs, extents, cell_size, resample="near"):
    xmin, ymin, xmax, ymax = extents
    result = gdal.Warp(
        dst, src,
        options=gdal.WarpOptions(
            dstSRS=crs,
            outputBounds=(xmin, ymin, xmax, ymax),
            xRes=cell_size, yRes=cell_size,
            resampleAlg=resample,
            targetAlignedPixels=True,
        ),
    )
    if result is None:
        raise RuntimeError(f"gdal.Warp failed: {src} -> {dst}")
    result.FlushCache()
    del result


def _read_raster(path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Raster not found: {path}")
    with rioxarray.open_rasterio(path) as src:
        da = src.squeeze(dim="band", drop=True)
    return da


def _basin_mask(polygon, dem_da):
    """Rasterize basin polygon onto the DEM grid. Returns uint8 array."""
    gdf = gpd.read_file(polygon)
    ny, nx = dem_da.shape
    return rasterize(
        gdf.geometry,
        out_shape=(ny, nx),
        transform=dem_da.rio.transform(),
        fill=0,
        default_value=1,
        dtype="uint8",
    )


def _veg_tau_k(evt_arr, veg_params_csv):
    """Map EVT pixel values → tau and k arrays using the veg params CSV."""
    df = pd.read_csv(veg_params_csv)
    idx_col = "landfire140" if "landfire140" in df.columns else df.columns[0]
    df = df.set_index(idx_col)
    df = df[~df.index.duplicated(keep="first")]

    missing = set(np.unique(evt_arr)) - set(df.index)
    if missing:
        # tau/k have no safe fallback — missing class would silently corrupt radiation
        raise ValueError(f"EVT classes not in {veg_params_csv}: {missing}")

    flat = pd.Series(evt_arr.ravel())
    tau = flat.map(df["tau"]).values.reshape(evt_arr.shape)
    k = flat.map(df["k"]).values.reshape(evt_arr.shape)
    return tau, k


def _veg_height(evh_arr, evh_csv):
    """Parse mean canopy heights from the LANDFIRE EVH CLASSNAMES CSV; defaults to 0 m."""
    df = pd.read_csv(evh_csv).set_index("VALUE")
    def _parse_height(s):
        matches = _HEIGHT_RE.findall(str(s))
        return float(np.mean([float(x) for x in matches])) if matches else 0.0

    df["height"] = df["CLASSNAMES"].apply(_parse_height)
    mapped = pd.Series(evh_arr.ravel()).map(df["height"]).fillna(0.0)
    return mapped.values.reshape(evh_arr.shape)


def _projection_var(crs_str):
    """
    Build a CF grid_mapping scalar DataArray from a CRS string. WKT is in version WKT1 for compatibility with WindNinja and older GDAL versions. The WKT is included in both crs_wkt and spatial_ref attributes for maximum compatibility.
    """
    crs = CRS.from_string(crs_str)
    wkt = crs.to_wkt(version="WKT1_GDAL")
    attrs = crs.to_cf()
    attrs["crs_wkt"] = wkt
    attrs["spatial_ref"] = wkt
    # smrf/data/load_topo.py requires utm_zone_number as an integer attribute
    epsg = crs.to_epsg()
    if epsg and 32601 <= epsg <= 32660:
        attrs["utm_zone_number"] = epsg - 32600
    elif epsg and 32701 <= epsg <= 32760:
        attrs["utm_zone_number"] = epsg - 32700
    return xr.DataArray(0, attrs=attrs)


def validate(topo_nc, expected_epsg):
    with xr.open_dataset(topo_nc) as ds:
        if "projection" not in ds:
            raise RuntimeError("topo.nc missing 'projection' variable")
        proj_attrs = ds["projection"].attrs
        wkt = proj_attrs.get("crs_wkt") or proj_attrs.get("spatial_ref")
        if not wkt:
            raise RuntimeError("topo.nc 'projection' has no crs_wkt or spatial_ref attribute")
        actual = CRS.from_wkt(wkt).to_epsg()
    if actual != expected_epsg:
        raise ValueError(f"topo.nc CRS mismatch: EPSG:{actual} != expected EPSG:{expected_epsg}")
    print(f"  Projection OK, EPSG:{actual}")


def build_topo(polygon, dem_file, landfire_dir, veg_params_csv,
                  output_dir, cell_size, basin_name, veg_dir=None):
    """Construct topo.nc from input files and write to output_dir. Returns topo.nc path."""
    if veg_dir is not None:
        veg_dir = Path(veg_dir)
        missing = [fname for fname, _ in VEG_DIR_FILES.values() if not (veg_dir / fname).exists()]
        if missing:
            expected = "\n".join(f"  {fname}" for fname, _ in VEG_DIR_FILES.values())
            raise FileNotFoundError(
                f"Missing files in {veg_dir}:\n"
                + "\n".join(f"  {f}" for f in missing)
                + f"\nExpected layout:\n{expected}"
            )

    landfire_dir = Path(landfire_dir)
    topo_output = Path(output_dir) / f"output_{int(cell_size)}m"
    temp_dir = topo_output / "temp"
    topo_output.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(exist_ok=True)

    print("Computing extents...")
    extents, crs = _padded_extents(polygon, cell_size)

    print("Clipping DEM...")
    dem_clip = str(temp_dir / "clipped_dem.tif")
    _clip_raster(str(dem_file), dem_clip, crs, extents, cell_size, "bilinear")
    dem_da = _read_raster(dem_clip)
    coords = {"y": dem_da.y, "x": dem_da.x}

    mask_arr = _basin_mask(polygon, dem_da)

    if veg_dir is not None:
        print("Clipping user-provided vegetation rasters to basin extents...")
        clips = {}
        for var, (fname, resample) in VEG_DIR_FILES.items():
            clip_path = str(temp_dir / f"clipped_{var}.tif")
            _clip_raster(str(veg_dir / fname), clip_path, crs, extents, cell_size, resample)
            clips[var] = _read_raster(clip_path).values
        type_arr   = clips["veg_type"]
        height_arr = clips["veg_height"]
        tau_arr    = clips["veg_tau"]
        k_arr      = clips["veg_k"]
    else:
        print("Clipping LANDFIRE vegetation to basin extents...")
        evt_clip = str(temp_dir / "clipped_veg_type.tif")
        evh_clip = str(temp_dir / "clipped_veg_height.tif")
        _clip_raster(str(landfire_dir / _EVT_PATH), evt_clip, crs, extents, cell_size, "near")
        _clip_raster(str(landfire_dir / _EVH_PATH), evh_clip, crs, extents, cell_size, "near")
        evt_da = _read_raster(evt_clip)
        evh_da = _read_raster(evh_clip)
        type_arr = evt_da.values
        tau_arr, k_arr = _veg_tau_k(type_arr, veg_params_csv)
        height_arr = _veg_height(evh_da.values, str(landfire_dir / _EVH_CSV))

    print("Assembling dataset...")
    ds = xr.Dataset({
        "dem": xr.DataArray(
            dem_da.values, dims=["y", "x"], coords=coords,
            attrs={"long_name": "dem"}),
        "mask": xr.DataArray(
            mask_arr, dims=["y", "x"], coords=coords,
            attrs={"long_name": basin_name}),
        "veg_type": xr.DataArray(
            type_arr, dims=["y", "x"], coords=coords,
            attrs={"long_name": "vegetation type"}),
        "veg_height": xr.DataArray(
            height_arr, dims=["y", "x"], coords=coords,
            attrs={"long_name": "vegetation height"}),
        "veg_tau": xr.DataArray(
            tau_arr, dims=["y", "x"], coords=coords,
            attrs={"long_name": "vegetation tau"}),
        "veg_k": xr.DataArray(
            k_arr, dims=["y", "x"], coords=coords,
            attrs={"long_name": "vegetation k"}),
        "projection": _projection_var(crs),
    })

    # Strip any grid_mapping set by rioxarray to avoid xarray encoding conflict
    for var in list(ds.data_vars) + list(ds.coords):
        ds[var].attrs.pop("grid_mapping", None)
        ds[var].encoding.pop("grid_mapping", None)

    ds.x.attrs = {"units": "meters", "long_name": "x coordinate",
                  "standard_name": "projection_x_coordinate"}
    ds.y.attrs = {"units": "meters", "long_name": "y coordinate",
                  "standard_name": "projection_y_coordinate"}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ds.attrs = {
        "Conventions": "CF-1.6",
        "dateCreated": now,
        "Title": "Topographic Images for SMRF/AWSM",
        "history": f"[{now}] Created by build_topo_nc.py",
    }

    topo_nc = topo_output / "topo.nc"
    print(f"Writing {topo_nc}...")
    ds.to_netcdf(
        topo_nc,
        format="NETCDF4",
        encoding={
            "x": {"dtype": "f8"},
            "y": {"dtype": "f8"},
            "dem": {"dtype": "f4", "grid_mapping": "projection"},
            "mask": {"grid_mapping": "projection"},
            "veg_type": {"dtype": "u2", "grid_mapping": "projection"},
            "veg_height": {"dtype": "f4", "grid_mapping": "projection"},
            "veg_tau": {"dtype": "f4", "grid_mapping": "projection"},
            "veg_k": {"dtype": "f4", "grid_mapping": "projection"},
        },
    )
    return topo_nc


def read_basin_env(output_dir):
    """Read key value pairs from basin.env into dict."""
    env_path = Path(output_dir) / "basin.env"
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"\'')
    return env


def main():
    parser = argparse.ArgumentParser(
        description="Build topo.nc from polygon + DEM + LANDFIRE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage="\n  build_topo_nc.py -s POLY -d DEM -o DIR [-res METERS] [--name NAME]\n"
              "  build_topo_nc.py -o DIR  # reads basin.env",
        epilog=__doc__,
    )
    parser.add_argument("-s", "--polygon", metavar="POLY",
                        help="Basin polygon file (shapefile or GeoPackage); reads BASIN_POLYGON from basin.env if omitted.")
    parser.add_argument("-d", "--dem-file", metavar="DEM",
                        help="Warped DEM GeoTIFF; reads BASIN_DEM from basin.env if omitted.")
    parser.add_argument("-o", "--output-dir", required=True, metavar="DIR")
    parser.add_argument("-res", "--cell-size", type=float, default=100.0, metavar="METERS")
    parser.add_argument("-e", "--epsg", type=int, default=None, metavar="EPSG",
                        help="UTM EPSG. Reads BASIN_EPSG from basin.env if omitted.")
    parser.add_argument("--name", default=None, metavar="NAME",
                        help="Basin name for mask; reads BASIN_NAME from basin.env if None.")
    parser.add_argument("--landfire-dir", default=str(LANDFIRE_DIR_DEFAULT), metavar="DIR")
    parser.add_argument("--veg-params-csv", default=str(VEG_PARAMS_CSV_DEFAULT), metavar="CSV")
    expected = ", ".join(fname for fname, _ in VEG_DIR_FILES.values())
    parser.add_argument("--veg-dir", default=None, metavar="DIR",
                        help=f"Directory of user-derived vegetation rasters, overrides "
                             f"--landfire-dir. Must contain: {expected}")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    env = read_basin_env(output_dir)

    polygon = Path(args.polygon) if args.polygon else Path(env.get("BASIN_POLYGON", ""))
    dem_file = Path(args.dem_file) if args.dem_file else Path(env.get("BASIN_DEM", ""))
    epsg = args.epsg or int(env.get("BASIN_EPSG", 0))
    basin_name = args.name or env.get("BASIN_NAME", "Full Basin")

    if not polygon or not polygon.exists():
        sys.exit(f"Polygon file not found: {polygon}. Pass -s or run fetch_basin.py first.")
    if not dem_file or not dem_file.exists():
        sys.exit(f"DEM file not found: {dem_file}. Pass -d or run fetch_dem.py first.")
    if not epsg:
        sys.exit("EPSG not found. Pass -e or run fetch_basin.py first.")

    landfire_dir = Path(args.landfire_dir)
    veg_params_csv = Path(args.veg_params_csv)
    if not args.veg_dir:
        if not landfire_dir.exists():
            sys.exit(f"LANDFIRE directory not found: {landfire_dir}")
        if not veg_params_csv.exists():
            sys.exit(f"veg_params_csv not found: {veg_params_csv}")

    topo_nc = build_topo(
        polygon, dem_file, landfire_dir, veg_params_csv,
        output_dir, args.cell_size, basin_name,
        veg_dir=args.veg_dir,
    )

    print("Validating projection...")
    validate(topo_nc, epsg)
    print(f"\nDone! topo.nc at {topo_nc}")


if __name__ == "__main__":
    main()
