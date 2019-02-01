import configparser


class Config:

    def __init__(self, config_files):
        self.__config = configparser.ConfigParser()
        self.__config.read(config_files)

    def __getitem__(self, pair):
        section, key = pair
        return self.__config.get(section, key)


def as_list(value, type=int):
    return [type(m) for m in value.split(",")]


config = Config(["config.ini", "config.ini.local"])
