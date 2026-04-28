# News
Overview of model component changes per release

# 20260309
## AWSM
* Updates test "gold" files with TopoCalc changes

## SMRF
* Uses `numexpr` library for thermal calculations
* Add option to allow vegetation adjustments for TopoSplit Longwave and Shortwave. This re-uses the existing `corr_veg` parameter in the corresponding `[thermal]` and `[solar]` ini file section
* Update test "gold" files with TopoCalc changes

### Release notes
https://github.com/iSnobal/smrf/releases/tag/20260309

## PySnobal
_None_

## TopoCalc
* Improve `skew()` function by using linear interpolation
* Update local topography equations to use [Dozier (2022)](https://doi.org/10.1109/LGRS.2021.3125278)

### Release notes
https://github.com/iSnobal/topocalc/releases/tag/20260309
