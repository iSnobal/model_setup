import fsspec
import h5netcdf
import numpy as np
import pytest

import wus_d3_download as script

REMOTE = "/wus_d3/hourly"
HOURS = ("auxhist_d01_2022-09-01_00:00:00", "auxhist_d01_2022-09-01_01:00:00")
SHAPE = (1, 4, 6)
# Variable of the hourly files that SMRF does not read
UNUSED = "SNOWNC"


def hourly_file(path, hour: int) -> bytes:
    """
    Content of a small hourly file with the SMRF variables, compressed like WUS-D3,
    and one variable that SMRF does not read.
    """
    with h5netcdf.File(path, "w") as hourly:
        hourly.dimensions = {
            "Time": SHAPE[0],
            "DateStrLen": 19,
            "south_north": SHAPE[1],
            "west_east": SHAPE[2],
        }
        hourly.attrs["TITLE"] = "hourly"
        times = hourly.create_variable("Times", ("Time", "DateStrLen"), "S1")
        times[:] = np.array([list(f"2022-09-01_0{hour}:00:00".encode())], dtype="u1").view("S1")
        for offset, name in enumerate((*script.VARIABLES[1:], UNUSED)):
            field = hourly.create_variable(
                name,
                ("Time", "south_north", "west_east"),
                "f4",
                data=np.arange(24).reshape(SHAPE) + offset + hour,
                chunks=(1, 2, 3),
                compression="gzip",
                compression_opts=2,
                shuffle=True,
            )
            field.attrs["units"] = name
    return path.read_bytes()


@pytest.fixture
def fs(tmp_path):
    """
    In-memory file system with two hourly files, removed after the test.
    """
    memory = fsspec.filesystem("memory")
    for hour, name in enumerate(HOURS):
        memory.pipe(f"{REMOTE}/{name}", hourly_file(tmp_path / name, hour))
    yield memory
    memory.rm(REMOTE, recursive=True)


class TestRunName:
    def test_bias_corrected(self):
        assert script.run_name("cesm2_r11i1p1f1", "ssp370", True) == "cesm2_r11i1p1f1_ssp370_bc"

    def test_not_bias_corrected(self):
        assert script.run_name("cesm2_r11i1p1f1", "ssp370", False) == "cesm2_r11i1p1f1_ssp370"


class TestSync:
    @pytest.mark.parametrize("batch_size", [1, script.BATCH_SIZE])
    def test_download(self, fs, tmp_path, batch_size):
        local = tmp_path / "run"
        script.sync(fs, REMOTE, str(local), batch_size)

        assert sorted(path.name for path in local.iterdir()) == [
            f"{name}{script.EXTENSION}" for name in HOURS
        ]

    def test_subset(self, fs, tmp_path):
        local = tmp_path / "run"
        script.sync(fs, REMOTE, str(local))

        source = tmp_path / HOURS[1]
        output = local / f"{HOURS[1]}{script.EXTENSION}"
        with h5netcdf.File(source, "r") as hourly, h5netcdf.File(output, "r") as subset:
            assert set(subset.variables) == set(script.VARIABLES)
            assert subset.attrs["TITLE"] == "hourly"
            for name in script.VARIABLES:
                np.testing.assert_array_equal(subset[name][:], hourly[name][:])
                assert dict(subset[name].attrs) == dict(hourly[name].attrs)
                assert subset[name].chunks == hourly[name].chunks
                assert subset[name].compression == hourly[name].compression

    def test_skip_downloaded(self, fs, tmp_path):
        downloaded = tmp_path / f"{HOURS[0]}{script.EXTENSION}"
        downloaded.write_bytes(b"downloaded")

        script.sync(fs, REMOTE, str(tmp_path))

        assert downloaded.read_bytes() == b"downloaded"

    def test_replace_partial(self, fs, tmp_path):
        partial = tmp_path / f"{HOURS[0]}{script.EXTENSION}{script.PARTIAL}"
        partial.write_bytes(b"partial")

        script.sync(fs, REMOTE, str(tmp_path))

        assert not partial.exists()
        assert (tmp_path / f"{HOURS[0]}{script.EXTENSION}").exists()
