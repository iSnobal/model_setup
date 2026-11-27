import h5netcdf
import numpy as np
import pytest

import wus_d3_metadata as script

SHAPE = (4, 3)


@pytest.fixture
def wrfinput(tmp_path):
    """
    Small WRF input file with one time step, the grid fields and grid attributes.
    """
    path = tmp_path / "wrfinput_d02"
    with h5netcdf.File(path, "w") as source:
        source.dimensions = {"Time": 1, script.ROWS: SHAPE[0], script.COLUMNS: SHAPE[1]}
        for offset, name in enumerate(script.GRID_VARIABLES):
            field = source.create_variable(
                name,
                ("Time", script.ROWS, script.COLUMNS),
                "f4",
                data=np.arange(12).reshape(1, *SHAPE) + offset,
            )
            field.attrs.update({"units": "unit", "description": name})
        source.attrs.update({key: 1.0 for key in script.PROJECTION_ATTRIBUTES})
        source.attrs["TITLE"] = "not a grid attribute"
    return path


class TestWriteMetadata:
    def test_grid_fields(self, wrfinput, tmp_path):
        output = tmp_path / "domain.nc"
        with h5netcdf.File(wrfinput, "r") as source:
            script.write_metadata(source, output)

        with h5netcdf.File(wrfinput, "r") as source, h5netcdf.File(output, "r") as metadata:
            for name in script.GRID_VARIABLES:
                np.testing.assert_array_equal(metadata[name][:], source[name][0])
                assert metadata[name].dimensions == (script.ROWS, script.COLUMNS)
                assert list(metadata[name].attrs) == list(script.VARIABLE_ATTRIBUTES)

    def test_attributes(self, wrfinput, tmp_path):
        output = tmp_path / "domain.nc"
        with h5netcdf.File(wrfinput, "r") as source:
            script.write_metadata(source, output)

        with h5netcdf.File(output, "r") as metadata:
            assert set(metadata.attrs) == {*script.PROJECTION_ATTRIBUTES, "source"}
