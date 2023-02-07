import logging
import os
import sys
from functools import cached_property
from pathlib import Path

from box import BoxError, ConfigBox

from .utils import ProxyBase

DEFAULT_CONF = {"path": {}, "requirement": {"schrodinger": ["run"]}, "detect_path": ["schrodinger"]}


logger = logging.getLogger("protactm")


class ConfigError(BoxError):
    pass


def _parse_req_env(req):
    patterns = (req.upper(), req.upper() + "_HOME", req.upper() + "_ROOT")
    for p in patterns:
        if p in os.environ and os.path.exists(os.environ[p]):
            logger.debug(f'Found requirement path "{req}" from envvar "{p}".')
            return os.environ[p]
    return None

class Config(ProxyBase):
    __noproxy__ = ('conf_file')
    
    def __init__(self, conf_file=None):
        self.conf_file = conf_file

    @cached_property
    def __subject__(self):
        return self.reload_conf(conf_file=self.conf_file)

    @staticmethod
    def reload_conf(box=None, conf_file=None):
        """Load config from provided file or config.yaml at cwd."""
        if not box:
            box = ConfigBox(DEFAULT_CONF, box_dots=True)
        if conf_file:
            conf_file = Path(conf_file)
        elif Path("./config.yaml").is_file():
            conf_file = Path("./config.yaml")
        else:
            logger.debug("No config found from provided file or ./config.yaml.")
        if conf_file:
            logger.debug(f'Loading config from "{conf_file}".')
            if not conf_file.suffix.lower() in (".yaml", ".yml"):
                box.merge_update(ConfigBox.from_yaml(filename=conf_file))
            else:
                logger.warning(f'Can not load config file "{conf_file}", a yaml file is required.')
        for v in box.detect_path:
            detected_path = _parse_req_env(v)
            if not detected_path:
                logger.warning(f'Path of "{v}" is not found from either envvar or config.')
            else:
                box.path[v] = detected_path
        for k, v in box.path.items():
            if v and k in box.requirement:
                if isinstance(box.requirement[k], str):
                    box.requirement[k] = [c.strip() for c in box.requirement[k].split(',')]
                for check in box.requirement[k]:
                    if not (Path(v) / check).exists():
                        logger.warning(f'Path of "{k}" does not meet the requirement, because:\n'+
                                       f'  - "{Path(v) / check}" does not exist.')
        return box

    def __getitem__(self, arg):
        while True:
            try:
                return self.__subject__[arg]
            except BoxError as e:
                raise ConfigError(f'can not find config key "{arg}", please check your config file or environment var.') from None

config = Config()
