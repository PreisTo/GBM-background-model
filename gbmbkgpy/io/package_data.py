import os
from pathlib import Path
from importlib.resources import files


def get_path_of_data_file(source_type, data_file):

    return files("gbmbkgpy") / "data/datasets/{0}/{1}".format(source_type, data_file)


def get_path_of_data_dir():

    return files("gbmbkgpy") / "data/datasets"


def get_path_of_external_data_dir():

    file_path = os.environ["GBMDATA"]

    return Path(file_path)


def get_path_of_external_data_file(source_type, data_file):

    file_path = get_path_of_external_data_dir() / source_type / data_file

    return file_path
