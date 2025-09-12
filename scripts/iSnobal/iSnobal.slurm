#!/bin/bash

#SBATCH --job-name=iSnobal
#SBATCH --account=owner-guest
#SBATCH --partition=notchpeak-guest

#SBATCH --time=1:00:00
#SBATCH --ntasks=24
#SBATCH --mem=4G

#SBATCH --mail-type=FAIL,END
#SBATCH --mail-user=user@utah.edu

#SBATCH --chdir=/path/to/scratch/
#SBATCH --output=slurm-%j.out-%N
#SBATCH --error=slurm-%j.err-%N

# Enable CPU Hyper-threading
export OMP_NUM_THREADS=${SLURM_NTASKS}

# Update the below use of conda according to the HPC docs
module load miniforge
mamba activate isnobal

awsm_daily ~/project-data/iSnobal/ERW/ERW_subset_awsm.ini
