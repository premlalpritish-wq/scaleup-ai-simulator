import pathlib

def pytest_configure(config):
    if not config.option.basetemp:
        temp_dir = pathlib.Path(".pytest_cache") / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = temp_dir
