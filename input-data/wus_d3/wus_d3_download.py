#!/usr/bin/env python3

import argparse
import io
import os

import fsspec
import h5netcdf
import s3fs

# WUS-D3 bucket and the folder of the 9 km hourly files for one run and year.
# Each year has data from September 1 of the year to September 1 of the next year
BUCKET = "wrf-cmip6-noversioning"
HOURLY_FOLDER = BUCKET + "/downscaled_products/gcm/{run}/hourly/{year}/d02"

# Scenarios of the WUS-D3 GCM runs
SCENARIOS = ("historical", "ssp245", "ssp370", "ssp585")
BIAS_CORRECTED = "_bc"

# Variables of the hourly files that SMRF reads
VARIABLES = (
    "Times",
    "T2",
    "Q2",
    "PSFC",
    "RAINNC",
    "RAINC",
    "U10",
    "V10",
    "SWDNB",
    "SWDNBC",
    "LWDNB",
)

# Number of hourly files held in memory at once
BATCH_SIZE = 80

# SMRF reads the hourly files with this extension, which the files on S3 do not have
EXTENSION = ".nc"
# Extension of a file while it is written, so an unfinished file is never read as done
PARTIAL = ".part"


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the WUS-D3 hourly files of a GCM run for one year, "
        "keeping only the variables SMRF reads. "
        "Files that are already downloaded are skipped."
    )
    parser.add_argument(
        "--gcm",
        "-g",
        required=True,
        type=str,
        help="GCM and variant, for example cesm2_r11i1p1f1",
    )
    parser.add_argument(
        "--scenario",
        "-s",
        required=True,
        choices=SCENARIOS,
        help="Scenario of the GCM run",
    )
    parser.add_argument(
        "--bias-corrected",
        "-b",
        action="store_true",
        help="Download the bias-corrected run",
    )
    parser.add_argument(
        "--water-year",
        "-y",
        required=True,
        type=int,
        help="Water year, for example 2021 for October 2020 to September 2021. "
        "September of the water year is not included.",
    )
    parser.add_argument(
        "--output",
        "-O",
        metavar="OUTPUT_FOLDER",
        type=str,
        default=".",
        help="Folder to create the run folder in",
    )
    parser.add_argument(
        "--batch-size",
        "-n",
        type=int,
        default=BATCH_SIZE,
        help="Number of files held in memory at once, about 4.5 MB each",
    )

    return parser


def run_name(gcm: str, scenario: str, bias_corrected: bool) -> str:
    """
    Get the WUS-D3 name of a GCM run.

    Parameters
    ----------
    gcm : str
        GCM and variant, for example cesm2_r11i1p1f1
    scenario : str
        Scenario of the run, one of SCENARIOS
    bias_corrected : bool
        True for the bias-corrected run

    Returns
    -------
    str
        Run name, for example cesm2_r11i1p1f1_ssp370_bc
    """
    name = f"{gcm}_{scenario}"
    if bias_corrected:
        name += BIAS_CORRECTED
    return name


def local_path(remote_path: str, local_folder: str) -> str:
    """
    Get the local path of an hourly file.

    Parameters
    ----------
    remote_path : str
        Path of the hourly file on the remote file system
    local_folder : str
        Folder for the downloaded files

    Returns
    -------
    str
        Path of the file in the local folder, with the SMRF extension
    """
    return os.path.join(local_folder, os.path.basename(remote_path) + EXTENSION)


def files_to_download(
    fs: fsspec.AbstractFileSystem, remote_folder: str, local_folder: str
) -> list[str]:
    """
    Get the hourly files of a remote folder that are not downloaded yet.

    Parameters
    ----------
    fs : fsspec.AbstractFileSystem
        File system with the hourly files
    remote_folder : str
        Folder with the hourly files
    local_folder : str
        Folder for the downloaded files

    Returns
    -------
    list of str
        Remote paths of the files to download
    """
    return [
        path
        for path in sorted(fs.ls(remote_folder))
        if not os.path.isfile(local_path(path, local_folder))
    ]


def copy_variable(source: h5netcdf.Variable, output: h5netcdf.File) -> None:
    """
    Copy a variable with its attributes to a file.

    Chunked variables keep the chunks and compression of the source, and their
    compressed chunks are copied as they are.

    Parameters
    ----------
    source : h5netcdf.Variable
        Variable to copy
    output : h5netcdf.File
        File open for writing, with the dimensions of the variable
    """
    # Settings are read from the HDF5 dataset, because h5netcdf scans the whole
    # file for the size of the unlimited Time dimension on every lookup
    dataset = source._h5ds
    if dataset.chunks is None:
        variable = output.create_variable(
            source.name, source.dimensions, source.dtype, data=source[:]
        )
    else:
        variable = output.create_variable(
            source.name,
            source.dimensions,
            source.dtype,
            chunks=dataset.chunks,
            compression=dataset.compression,
            compression_opts=dataset.compression_opts,
            shuffle=dataset.shuffle,
        )
        source_chunks = dataset.id
        output_chunks = variable._h5ds.id
        for index in range(source_chunks.get_num_chunks()):
            offset = source_chunks.get_chunk_info(index).chunk_offset
            filter_mask, chunk = source_chunks.read_direct_chunk(offset)
            output_chunks.write_direct_chunk(offset, chunk, filter_mask)

    variable.attrs.update(source.attrs)


def write_subset(content: bytes, output: str) -> None:
    """
    Write the SMRF variables of an hourly file to disk.

    The file only appears under its final name once it is complete.

    Parameters
    ----------
    content : bytes
        Content of the hourly file
    output : str
        Path of the file to write
    """
    partial = output + PARTIAL
    with (
        h5netcdf.File(io.BytesIO(content), "r") as source,
        h5netcdf.File(partial, "w") as subset,
    ):
        subset.dimensions = {
            name: size
            for variable in VARIABLES
            for name, size in zip(
                source.variables[variable].dimensions,
                source.variables[variable]._h5ds.shape,
            )
        }
        subset.attrs.update(source.attrs)
        for variable in VARIABLES:
            copy_variable(source.variables[variable], subset)
    os.replace(partial, output)


def sync(
    fs: fsspec.AbstractFileSystem,
    remote_folder: str,
    local_folder: str,
    batch_size: int = BATCH_SIZE,
) -> None:
    """
    Download the SMRF variables of the hourly files that are not downloaded yet.

    Parameters
    ----------
    fs : fsspec.AbstractFileSystem
        File system with the hourly files
    remote_folder : str
        Folder with the hourly files
    local_folder : str
        Folder for the downloaded files, created when missing
    batch_size : int
        Number of files held in memory at once
    """
    os.makedirs(local_folder, exist_ok=True)
    remote = files_to_download(fs, remote_folder, local_folder)
    print(f"Downloading {len(remote)} files from {remote_folder} to {local_folder}")

    for start in range(0, len(remote), batch_size):
        for path, content in fs.cat(remote[start : start + batch_size]).items():
            write_subset(content, local_path(path, local_folder))
        print(f"{min(start + batch_size, len(remote))} of {len(remote)} files done")


def main() -> None:
    args = argument_parser().parse_args()

    run = run_name(args.gcm, args.scenario, args.bias_corrected)
    sync(
        s3fs.S3FileSystem(anon=True),
        HOURLY_FOLDER.format(run=run, year=args.water_year - 1),
        os.path.join(args.output, run),
        args.batch_size,
    )


if __name__ == "__main__":
    main()
