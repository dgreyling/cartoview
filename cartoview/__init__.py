__version__ = (1, 5, 4, 'final', 0)
__compatible_with__ = []


def get_current_version():
    import geonode.version
    return geonode.version.get_version(__version__)
