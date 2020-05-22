import yaml


def path_from_locale(locale: str) -> str:
    path: str = ""
    if "fr" in locale.lower():
        path = "loc/french.yml"
    if len(path) == 0:
        raise ImportError("Invalid locale code: {}".format(locale))
    return path


def strings_import(language: str) -> dict:
    with open(path_from_locale(language), 'r+') as f:
        strings = yaml.safe_load(f)
    return strings
