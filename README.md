# iSnobal model setup and guides
This repository contains the model setup and guides for the iSnobal installation in
a conda environment. Current structure holds the following folders:

## Conda
The recommended way to install the conda environment is using the
[mamba](https://mamba.readthedocs.io/en/latest/index.html) package manager. This folder 
contains a YAML file for each required environment to run the model or one of its 
components.

A full setup of the model has up to three separate environments:
* [HRRR](scripts/HRRR/README.md)
  Download required forcing data
* [katana](scripts/katana/README.md)
  Run WindNinja to downscale wind data
* [iSnobal](conda/isnobal.yaml)
  Execute the model

More instructions on the environment setup can be found in the
[README.md](conda/README.md) file.

## Config

Sample `.ini` files for the iSnobal run configuration.


## Scripts

Helper scripts to download or prepare data and execute the model components.  
This includes example SLURM scripts for High Performance Compute (HPC) environments.
