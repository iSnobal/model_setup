## LANDFIRE Vegetation Data
This folder contains the input and generated csv used in the workflow in veg_param_assignment.ipynb.
Vegetation parameters are used to generate basin files (topo.nc) in the basin_setup workflow for iSnobal.

#### Files in this folder
`landfire_veg_param.csv`
- Source vegetation parameter table (input).
-Includes LANDFIRE class names, LANDFIRE codes, and existing tau/k values.
  
`landfire_veg_params_assigned.csv`
- Generated output from notebook.
- Adds canopy classification fields and assigned canopy transmissivity parameters.
- Does not overwrite original parameters

#### How this dataset is generated
The output CSV is produced by running veg_param_assignment.ipynb from top to bottom.

**Workflow summary:**
1. Read landfire_veg_param.csv.
2. Remove NoData rows from the table.
3. Assign a canopy class to each LANDFIRE class name using keyword matching.
4. Map canopy class to transmissivity parameters tau and k (following Link and Marks, 1999).
5. Fill missing tau/k values using assigned_tau/assigned_k.
6. Write output to landfire_veg_params_assigned.csv.
7. Reproducibility notes
8. The canopy keyword dictionary and class-priority order are defined in the notebook and directly affect assigned classes and parameters.
9. If you modify keyword mappings or priority/order, regenerate the output CSV and review differences.
10. Keep notebook and data updates in the same commit when possible to preserve provenance.

#### Citation
This workflow is based on canopy transmissivity parameter classes described in Link and Marks (1999), as documented in the notebook.
Link, T. and Marks, D. (1999), Distributed simulation of snowcover mass- and energy-balance in the boreal forest. Hydrol. Process., 13: 2439-2452. https://doi.org/10.1002/(SICI)1099-1085(199910)13:14/15<2439::AID-HYP866>3.0.CO;2-1