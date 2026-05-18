# News
Highlights model component changes per release. This is not a comprehensive list
and each linked release note should be consulted for a full list of changes.

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

# 20260126
## AWSM
* PySnobal API updates [PR#30](https://github.com/iSnobal/awsm/pull/30)

## SMRF
_None_

## PySnobal
* Re-activate point execution [PR#11](https://github.com/iSnobal/pysnobal/pull/9)

### Release notes
https://github.com/iSnobal/pysnobal/releases/tag/20260126

## TopoCalc
* Add support of OS X [PR#10](https://github.com/iSnobal/topocalc/pull/10)

# 20251208
## AWSM
* Improve command line interface [PR#24](https://github.com/iSnobal/awsm/pull/24)
* Remove unused config file options [PR#26](https://github.com/iSnobal/awsm/pull/26)

### Release notes
https://github.com/iSnobal/awsm/releases/tag/20251208

## SMRF
* Add HRRR Longwave and Shortwave as forcing input options
[PR#22](https://github.com/iSnobal/smrf/pull/22) and [PR#42](https://github.com/iSnobal/smrf/pull/42)
* Remove option to run SMRF in threaded mode [PR#23](https://github.com/iSnobal/smrf/pull/23)

### Release notes
https://github.com/iSnobal/smrf/releases/tag/20251208

## PySnobal
* Minor logging improvements

## TopoCalc
_None_
