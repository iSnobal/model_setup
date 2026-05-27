#!/usr/bin/env python
"""
Build a UTM-projected DEM mosaic from USGS 3DEP 1/3 arc-second tiles.

By default, tiles are streamed via GDAL vsicurl without writing to disk.
Use --download-tiles for SLURM jobs where compute nodes lack internet access.

Reads basin.env from the output directory (written by fetch_basin.py) for
EPSG and bounding box if not provided explicitly. Appends BASIN_DEM to basin.env.

Usage:
    python fetch_dem.py -o ./newfork_scripts
    python fetch_dem.py -o ./newfork_scripts --download-tiles
    python fetch_dem.py -o ./newfork_scripts --download-tiles --skip-download
"""

import argparse
import sys
from pathlib import Path

import requests
from osgeo import gdal


TNM_DATASET = "National Elevation Dataset (NED) 1/3 arc-second"
TNM_API = "https://tnmaccess.nationalmap.gov/api/v1/products"


def read_basin_env(output_dir):
    """Parse key=value pairs from basin.env into a dict."""
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


def _query_tile_urls(bbox_wgs84):
    """Query TNM API, deduplicate by tile cell, and return .tif download URLs."""
    xmin, ymin, xmax, ymax = bbox_wgs84
    resp = requests.get(TNM_API, params={
        "datasets": TNM_DATASET,
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "max": 1000,
        "outputFormat": "JSON",
    }, timeout=60)
    resp.raise_for_status()

    items = resp.json().get("items", [])
    if not items:
        raise RuntimeError(f"No TNM DEM tiles found for bbox {bbox_wgs84}.")
    print(f"  Found {len(items)} DEM tile(s)")

    # Keep only the newest version of each tile cell
    # Title format: "USGS 1/3 Arc Second n40w107 20210312" → cell is second-to-last word
    best = {}
    for item in items:
        parts = item.get("title", "").split()
        tile = parts[-2] if len(parts) >= 2 else item.get("downloadURL", item.get("title", ""))
        pub_date = item.get("publicationDate", "")
        is_newer = tile in best and pub_date > best[tile].get("publicationDate", "")
        if tile not in best or is_newer:
            best[tile] = item
    deduped = list(best.values())
    print(f"  {len(deduped)} unique tile(s) after deduplication")

    # Prefer .tif — GDAL reads it directly; other formats may require format conversion
    tif_items = [i for i in deduped if i.get("downloadURL", "").endswith(".tif")]
    return [i["downloadURL"] for i in (tif_items or deduped)]


def stream_dem_tiles(bbox_wgs84):
    """Return vsicurl paths for GDAL to stream tiles without downloading."""
    urls = _query_tile_urls(bbox_wgs84)
    return [f"/vsicurl/{url}" for url in urls]


def download_dem_tiles(bbox_wgs84, output_dir):
    """Download tiles to disk and return local file paths."""
    urls = _query_tile_urls(bbox_wgs84)
    tile_dir = output_dir / "dem_tiles"
    tile_dir.mkdir(exist_ok=True)
    tile_files = []
    for url in urls:
        dest = tile_dir / Path(url).name
        if not dest.exists():
            print(f"    Downloading {dest.name} ...")
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        else:
            print(f"    {dest.name} already exists, skipping")
        tile_files.append(str(dest))
    return tile_files


def build_dem(tile_files, epsg, cell_size, output_dir):
    """Mosaic tiles and warp to target UTM/resolution. Returns output GeoTIFF path."""
    vrt_path = str(output_dir / "dem_mosaic.vrt")
    dem_path = output_dir / f"dem_epsg_{epsg}_{int(cell_size)}m.tif"

    print(f"  Building VRT from {len(tile_files)} tile(s)...")
    vrt = gdal.BuildVRT(vrt_path, tile_files)
    if vrt is None:
        raise RuntimeError("gdal.BuildVRT failed")
    vrt.FlushCache()
    del vrt

    print(f"  Warping to EPSG:{epsg} at {int(cell_size)}m...")
    result = gdal.Warp(
        str(dem_path), vrt_path,
        options=gdal.WarpOptions(
            dstSRS=f"EPSG:{epsg}",
            xRes=cell_size, yRes=cell_size,
            resampleAlg="cubicspline",
            targetAlignedPixels=True,
            creationOptions=["TILED=YES", "COMPRESS=LZW", "BIGTIFF=IF_SAFER"],
        ),
    )
    if result is None:
        raise RuntimeError("gdal.Warp failed")
    result.FlushCache()
    del result
    return dem_path


def main():
    parser = argparse.ArgumentParser(
        description="Build a UTM-projected DEM mosaic from USGS 3DEP tiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=("\n  fetch_dem.py -o DIR [-res METERS] [-e EPSG]"
               " [--download-tiles]"),
        epilog=__doc__,
    )
    parser.add_argument("-o", "--output-dir", required=True, metavar="DIR",
                        help="Output directory (reads basin.env from here)")
    parser.add_argument("-res", "--cell-size", type=float, default=100.0, metavar="METERS",
                        help="Resolution in meters (default: 100)")
    parser.add_argument("-e", "--epsg", type=int, default=None, metavar="EPSG",
                        help="UTM EPSG — reads BASIN_EPSG from basin.env if not given")
    parser.add_argument("--download-tiles", action="store_true",
                        help="Download tiles to disk before warping (use for SLURM/offline)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    env = read_basin_env(output_dir)

    epsg = args.epsg or int(env.get("BASIN_EPSG", 0))
    if not epsg:
        sys.exit("EPSG not provided and BASIN_EPSG not in basin.env. "
                 "Run fetch_basin.py first or pass -e EPSG.")

    bbox_str = env.get("BASIN_BBOX", "")
    if not bbox_str:
        sys.exit("BASIN_BBOX not in basin.env. Run fetch_basin.py first.")
    bbox_wgs84 = tuple(float(x) for x in bbox_str.split(","))

    if args.download_tiles:
        print("Downloading 3DEP 1/3 arc-second DEM tiles...")
        tile_files = download_dem_tiles(bbox_wgs84, output_dir)
    else:
        print("Streaming 3DEP 1/3 arc-second DEM tiles via vsicurl...")
        tile_files = stream_dem_tiles(bbox_wgs84)

    print(f"Building DEM mosaic (EPSG:{epsg}, {int(args.cell_size)}m)...")
    dem_path = build_dem(tile_files, epsg, args.cell_size, output_dir)
    print(f"DEM: {dem_path}")

    with open(output_dir / "basin.env", "a", encoding="utf-8") as f:
        f.write(f'BASIN_DEM="{dem_path}"\n')


if __name__ == "__main__":
    main()
