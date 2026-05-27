#!/usr/bin/env python
"""
Fetch a HUC watershed boundary from the USGS Water Boundary Dataset (WBD)
and save as a UTM-projected GeoPackage.

Writes <output-dir>/basin.env with BASIN_POLYGON, BASIN_EPSG, BASIN_BBOX,
and BASIN_NAME for use by fetch_dem.py and build_topo_nc.py.

Example usage:
    python fetch_basin.py -huc 14040102 -o ./newfork_scripts
    python fetch_basin.py -n "new fork" -o ./newfork_scripts [-level 8]
    python fetch_basin.py -s custom.gpkg -o ./newfork_scripts
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import requests

WBD_BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"
_WBD_LAYER = {2: 1, 4: 2, 6: 3, 8: 4, 10: 5, 12: 6}
WBD_FIELD = {2: "huc2", 4: "huc4", 6: "huc6", 8: "huc8", 10: "huc10", 12: "huc12"}


def _wbd_query(layer, where, out_fields):
    resp = requests.get(
        f"{WBD_BASE}/{layer}/query",
        params={"where": where, "outFields": out_fields, "f": "geojson"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"WBD API error: {data['error'].get('message', data['error'])}")
    features = data.get("features", [])
    if not features:
        return gpd.GeoDataFrame()
    return gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")


def utm_epsg_from_lonlat(lon, lat):
    zone = int((lon + 180) / 6) + 1
    return 32600 + zone if lat >= 0 else 32700 + zone


def fetch_huc_polygon(huc_id, output_dir):
    """Query WBD for a HUC boundary, reproject to UTM, and save as GeoPackage."""
    huc_level = len(huc_id)
    if huc_level not in _WBD_LAYER:
        raise ValueError(f"HUC ID length {huc_level} not supported. Use HUC2/4/6/8/10/12.")
    field = WBD_FIELD[huc_level]
    gdf = _wbd_query(_WBD_LAYER[huc_level], f"{field}='{huc_id}'", "*")
    if gdf.empty:
        raise ValueError(f"No WBD features found for HUC ID '{huc_id}'")

    xmin, ymin, xmax, ymax = gdf.total_bounds
    utm_epsg = utm_epsg_from_lonlat((xmin + xmax) / 2, (ymin + ymax) / 2)
    bbox_wgs84 = (xmin, ymin, xmax, ymax)
    basin_name = gdf.iloc[0].get("name", f"HUC{huc_id}")

    gpkg_path = output_dir / f"huc{huc_id}_basin.gpkg"
    gdf[["geometry"]].to_crs(f"EPSG:{utm_epsg}").to_file(gpkg_path, driver="GPKG")
    return gpkg_path, utm_epsg, bbox_wgs84, basin_name


def search_huc_by_name(name, huc_level=8):
    """Search WBD for HUCs with a name matching the input string (case-insensitive)."""
    if huc_level not in _WBD_LAYER:
        raise ValueError(f"huc_level {huc_level} not supported.")
    field = WBD_FIELD[huc_level]
    return _wbd_query(
        _WBD_LAYER[huc_level],
        f"LOWER(name) LIKE LOWER('%{name}%')",
        f"{field},name,areasqkm,states",
    )


def write_env(output_dir, polygon, epsg, bbox_wgs84, basin_name):
    """Write shell-sourceable key=value file for downstream scripts."""
    xmin, ymin, xmax, ymax = bbox_wgs84
    env_path = output_dir / "basin.env"
    env_path.write_text(
        f'BASIN_POLYGON="{polygon}"\n'
        f'BASIN_EPSG="{epsg}"\n'
        f'BASIN_BBOX="{xmin},{ymin},{xmax},{ymax}"\n'
        f'BASIN_NAME="{basin_name}"\n',
        encoding="utf-8",
    )
    return env_path


def main():
    parser = argparse.ArgumentParser(
        description="Fetch HUC watershed boundary → UTM polygon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        usage="\n  fetch_basin.py (-huc HUC_ID | -n NAME | -s POLY) -o DIR [-level N] [-e EPSG]",
        epilog=__doc__,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("-huc", "--huc-id", metavar="HUC_ID",
                     help="HUC ID (e.g. 14050001)")
    src.add_argument("-n", "--basin-name", metavar="NAME",
                     help="Basin name keyword to search (e.g. 'Yampa')")
    src.add_argument("-s", "--polygon", metavar="POLY",
                     help="Path to existing basin polygon file (shapefile or GeoPackage, must be in UTM)")
    parser.add_argument("-o", "--output-dir", required=True, metavar="DIR")
    parser.add_argument("-level", "--huc-level", type=int, default=8,
                        choices=[2, 4, 6, 8, 10, 12],
                        help="HUC level for -n search (default: 8)")
    parser.add_argument("-e", "--epsg", type=int, default=None,
                        help="Override UTM EPSG (auto-detected from centroid if not given)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.huc_id:
        print(f"Fetching HUC {args.huc_id} from USGS WBD...")
        polygon, utm_epsg, bbox_wgs84, basin_name = fetch_huc_polygon(
            args.huc_id, output_dir)

    elif args.basin_name:
        print(f"Searching USGS WBD HUC{args.huc_level} for '{args.basin_name}'...")
        matches = search_huc_by_name(args.basin_name, args.huc_level)
        huc_field = WBD_FIELD[args.huc_level]
        if matches.empty:
            sys.exit(f"No HUC{args.huc_level} features found matching '{args.basin_name}'.\n"
                     "Try a different spelling or -level.")
        if len(matches) > 1:
            cols = [c for c in [huc_field, "name", "areasqkm", "states"] if c in matches.columns]
            print(f"\n{len(matches)} matches for '{args.basin_name}':\n")
            print(matches[cols].to_string(index=False))
            sys.exit("\nRerun with the correct -huc value from the table above.")
        huc_id = matches[huc_field].iloc[0]
        basin_name = matches["name"].iloc[0]
        print(f"Found: {basin_name} ({huc_id})")
        polygon, utm_epsg, bbox_wgs84, _ = fetch_huc_polygon(huc_id, output_dir)

    else:
        polygon = Path(args.polygon).resolve()
        if not polygon.exists():
            sys.exit(f"Polygon file not found: {polygon}")
        gdf = gpd.read_file(polygon)
        if gdf.crs is None:
            sys.exit(
                f"Polygon file must have a defined projected CRS: {polygon}"
            )
        if not gdf.crs.is_projected:
            sys.exit(
                f"Polygon CRS must be projected/UTM, not geographic: {gdf.crs}"
            )
        polygon_epsg = gdf.crs.to_epsg()
        if polygon_epsg is None:
            sys.exit(
                f"Polygon CRS must resolve to an EPSG code so it can be validated: {gdf.crs}"
            )
        gdf_wgs84 = gpd.read_file(polygon).to_crs("EPSG:4326")
        xmin, ymin, xmax, ymax = gdf_wgs84.total_bounds
        lon_center = (xmin + xmax) / 2
        lat_center = (ymin + ymax) / 2
        expected_epsg = args.epsg or utm_epsg_from_lonlat(lon_center, lat_center)
        if polygon_epsg != expected_epsg:
            sys.exit(
                "Polygon CRS EPSG does not match the target UTM EPSG "
                f"(polygon: EPSG:{polygon_epsg}, expected: EPSG:{expected_epsg})"
            )
        utm_epsg = expected_epsg
        bbox_wgs84 = (xmin, ymin, xmax, ymax)
        basin_name = polygon.stem

    if args.epsg:
        utm_epsg = args.epsg

    env_path = write_env(output_dir, polygon, utm_epsg, bbox_wgs84, basin_name)
    print(f"Basin file: {polygon}")
    print(f"EPSG      : {utm_epsg}")
    print(f"Env file  : {env_path}")


if __name__ == "__main__":
    main()
