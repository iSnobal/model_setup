#!/usr/bin/env python3

import argparse

import h5netcdf
import s3fs

# WUS-D3 bucket and the WRF input file of the 9 km grid used by the hourly files
BUCKET = "wrf-cmip6-noversioning"
GRID_FILE = f"{BUCKET}/downscaled_products/wrf_coordinates/wrfinput_d02"

# Read size for each S3 request. The default of 50 MB fetches half the file.
BLOCK_SIZE = 2**20

# Grid fields missing from the WUS-D3 hourly files
GRID_VARIABLES = ("XLAT", "XLONG", "HGT")

# Variable attributes copied from the WRF input file
VARIABLE_ATTRIBUTES = ("units", "description")

# Global attributes that define the Lambert conformal projection of the grid
PROJECTION_ATTRIBUTES = (
    "MAP_PROJ",
    "TRUELAT1",
    "TRUELAT2",
    "STAND_LON",
    "CEN_LAT",
    "CEN_LON",
    "DX",
    "DY",
)

ROWS = "south_north"
COLUMNS = "west_east"


def write_metadata(source: h5netcdf.File, output: str) -> None:
    """
    Write the grid fields and projection of a WRF input file to a metadata file.

    Parameters
    ----------
    source : h5netcdf.File
        Open WRF input file with XLAT, XLONG and HGT
    output : str
        Path of the metadata file to write
    """
    with h5netcdf.File(output, "w") as metadata:
        metadata.dimensions = {
            ROWS: source.dimensions[ROWS].size,
            COLUMNS: source.dimensions[COLUMNS].size,
        }

        for name in GRID_VARIABLES:
            field = source.variables[name]
            variable = metadata.create_variable(
                name, (ROWS, COLUMNS), field.dtype, data=field[0], compression="gzip"
            )
            variable.attrs.update(
                {key: field.attrs[key] for key in VARIABLE_ATTRIBUTES}
            )

        metadata.attrs.update({key: source.attrs[key] for key in PROJECTION_ATTRIBUTES})
        metadata.attrs["source"] = f"s3://{GRID_FILE}"


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a wrf_metadata file with the WUS-D3 9 km grid fields"
    )
    parser.add_argument(
        "--output",
        "-O",
        metavar="OUTPUT_FILE",
        type=str,
        default="./WUS-D3_domain.nc",
        help="Output file path for the metadata file",
    )

    return parser


def main() -> None:
    args = argument_parser().parse_args()

    s3 = s3fs.S3FileSystem(anon=True)
    with (
        s3.open(GRID_FILE, block_size=BLOCK_SIZE) as remote,
        h5netcdf.File(remote, "r") as source,
    ):
        write_metadata(source, args.output)


if __name__ == "__main__":
    main()
