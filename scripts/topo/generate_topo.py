#!/usr/bin/env python
"""
Generate topo.nc for SMRF/iSnobal from a HUC ID, basin name, or polygon.

Chains fetch_basin → fetch_dem → build_topo_nc, passing values directly
between steps. Writes basin.env to the output directory for reference.

Example usage:
    python generate_topo.py -n "new fork" -o ./newfork_scripts
    python generate_topo.py -huc 14040102 -o ./newfork_scripts
    python generate_topo.py -s custom.gpkg -o ./newfork_scripts [-res 50]
"""

import argparse
import os
import sys
from pathlib import Path

# Allow sibling scripts to be imported regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

import geopandas as gpd

import build_topo_nc as btopo
import fetch_basin as fb
import fetch_dem as fd


def main():
    parser = argparse.ArgumentParser(
        description="Generate topo.nc for SMRF/iSnobal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage=(
            "\n"
            "  generate_topo.py (-huc HUC_ID | -n NAME | -s POLY) -o DIR\n"
            "                   [-res METERS] [-level {2,4,6,8,10,12}] [-e EPSG]\n"
            "                   [--landfire-dir DIR] [--veg-params-csv CSV | --veg-dir DIR]\n"
            "                   [--download-dem-tiles] [--skip-dem-download]"
        ),
        epilog=__doc__,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("-huc", "--huc-id", metavar="HUC_ID", help="HUC ID (e.g. 14050001)")
    src.add_argument("-n", "--basin-name", metavar="NAME", help="Basin keyword to search")
    src.add_argument("-s", "--polygon", metavar="POLY",
                     help="Pre-existing basin polygon file (shapefile or GeoPackage) in UTM")
    parser.add_argument("-o", "--output-dir", required=True, metavar="DIR")
    parser.add_argument("-res", "--cell-size", type=float, default=100.0, metavar="METERS")
    parser.add_argument("-level", "--huc-level", type=int, default=8,
                        choices=[2, 4, 6, 8, 10, 12],
                        help="HUC level for -n search (default: 8)")
    parser.add_argument("-e", "--epsg", type=int, default=None, metavar="EPSG",
                        help="Override auto-detected UTM EPSG")
    parser.add_argument("--landfire-dir", default=str(btopo.LANDFIRE_DIR_DEFAULT), metavar="DIR")
    parser.add_argument("--veg-params-csv", default=str(btopo.VEG_PARAMS_CSV_DEFAULT), metavar="CSV")
    parser.add_argument("--download-dem-tiles", action="store_true",
                        help="Download DEM tiles to disk before warping (use for SLURM/offline)")
    parser.add_argument("--skip-dem-download", action="store_true",
                        help="Reuse existing tiles in <output-dir>/dem_tiles/ (from previous run w/ --download-dem-tiles)")
    expected = ", ".join(fname for fname, _ in btopo.VEG_DIR_FILES.values())
    parser.add_argument("--veg-dir", default=None, metavar="DIR",
                        help=f"Directory of user-derived vegetation rasters, overrides "
                             f"--landfire-dir. Must contain: {expected}")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    landfire_dir = Path(args.landfire_dir)
    veg_params_csv = Path(args.veg_params_csv)

    if not args.veg_dir:
        if not landfire_dir.exists():
            sys.exit(f"LANDFIRE directory not found: {landfire_dir}")
        if not veg_params_csv.exists():
            sys.exit(f"veg_params_csv not found: {veg_params_csv}")

    print("\n[1/3] Fetching basin boundary...")
    if args.huc_id:
        polygon, utm_epsg, bbox_wgs84, basin_name = fb.fetch_huc_polygon(
            args.huc_id, output_dir)

    elif args.basin_name:
        matches = fb.search_huc_by_name(args.basin_name, args.huc_level)
        huc_field = fb.WBD_FIELD[args.huc_level]
        if matches.empty:
            sys.exit(f"No HUC{args.huc_level} features found matching '{args.basin_name}'.")
        if len(matches) > 1:
            cols = [c for c in [huc_field, "name", "areasqkm", "states"]
                    if c in matches.columns]
            print(f"\n  {len(matches)} matches for '{args.basin_name}':\n")
            print(matches[cols].to_string(index=False))
            sys.exit("\nRerun with the correct -huc value from the table above.")
        huc_id = matches[huc_field].iloc[0]
        basin_name = matches["name"].iloc[0]
        print(f"  Found: {basin_name} ({huc_id})")
        polygon, utm_epsg, bbox_wgs84, _ = fb.fetch_huc_polygon(huc_id, output_dir)

    else:
        polygon = Path(args.polygon).resolve()
        if not polygon.exists():
            sys.exit(f"Basin file not found: {polygon}")
        gdf_wgs84 = gpd.read_file(polygon).to_crs("EPSG:4326")
        xmin, ymin, xmax, ymax = gdf_wgs84.total_bounds
        lon_center = (xmin + xmax) / 2
        lat_center = (ymin + ymax) / 2
        utm_epsg = fb.utm_epsg_from_lonlat(lon_center, lat_center)
        bbox_wgs84 = (xmin, ymin, xmax, ymax)
        basin_name = polygon.stem

    if args.epsg:
        utm_epsg = args.epsg

    fb.write_env(output_dir, polygon, utm_epsg, bbox_wgs84, basin_name)
    print(f"  Basin file: {polygon}")
    print(f"  EPSG      : {utm_epsg}")

    print("\n[2/3] Building DEM...")
    if args.skip_dem_download:
        tile_files = [str(p) for p in (output_dir / "dem_tiles").glob("*.tif")]
        print(f"  Reusing {len(tile_files)} existing tile(s)")
        if not tile_files:
            sys.exit(f"No tiles in {output_dir / 'dem_tiles'}. Remove --skip-dem-download.")
    elif args.download_dem_tiles:
        tile_files = fd.download_dem_tiles(bbox_wgs84, output_dir)
    else:
        tile_files = fd.stream_dem_tiles(bbox_wgs84)

    dem_file = fd.build_dem(tile_files, utm_epsg, args.cell_size, output_dir)
    print(f"  DEM: {dem_file}")

    with open(output_dir / "basin.env", "a", encoding="utf-8") as f:
        f.write(f'BASIN_DEM="{dem_file}"\n')

    print("\n[3/3] Building topo.nc...")
    topo_nc = btopo.build_topo(
        polygon, dem_file, landfire_dir, veg_params_csv,
        output_dir, args.cell_size, basin_name,
        veg_dir=args.veg_dir,
    )

    print("\nValidating projection...")
    btopo.validate(topo_nc, utm_epsg)
    print(f"\nDone! topo.nc at {topo_nc}")

    # TODO: add --cleanup flag to remove intermediate files (dem_mosaic.vrt, warped DEM .tif,
    #       dem_tiles/, output_<res>m/temp/) after successful topo.nc generation


if __name__ == "__main__":
    main()
