import re, os

from enum import Enum

from .AttrDict import AttrDict
from .JsonIO import JsonIO

from .ModuleNote import ModuleNote
from .ModuleFeatures import ModuleFeatures
from .ModuleManager import ModuleManager
from .RootSolutions import RootSolutions
from .TrackOptions import TrackOptions

class TrackJson(AttrDict, JsonIO):
    id: str
    enable: bool
    verified: bool
    update_to: str
    changelog: str
    license: str
    homepage: str
    source: str
    support: str
    donate: str
    max_num: int
    download_source: str

    # FoxMMM supported props
    maxApi: int
    minApi: int
    
    # MMRL supported props
    category: str
    categories: list[str]
    icon: str
    homepage: str
    donate: str
    support: str
    cover: str
    screenshots: list[str]
    license: str
    screenshots: list[str]
    readme: str
    require: list[str]
    arch: list[str]
    devices: list[str]
    verified: bool
    note: ModuleNote
    features: ModuleFeatures
    root: RootSolutions
    manager: ModuleManager
    
    antifeatures: list[str]
    
    options: TrackOptions
    build_metadata: str

    # noinspection PyAttributeOutsideInit
    @property
    def type(self):
        if self._type is not None:
            return self._type

        if self.update_to.startswith("http"):
            if self.update_to.endswith(".json"):
                self._type = TrackType.ONLINE_JSON
            elif self.update_to.endswith(".zip"):
                self._type = TrackType.ONLINE_ZIP
            elif self.update_to.endswith(".git"):
                self._type = TrackType.GIT

        elif self.update_to.startswith("git@"):
            if self.update_to.endswith(".git"):
                self._type = TrackType.GIT

        else:
            if self.update_to.endswith(".json"):
                self._type = TrackType.LOCAL_JSON
            elif self.update_to.endswith(".zip"):
                self._type = TrackType.LOCAL_ZIP

        if self._type is None:
            self._type = TrackType.UNKNOWN

        return self._type

    def json(self, config, module_folder):
        return AttrDict(
            type=self.type.name,
            added=self.added,
            source=self.source or None,
            antifeatures=self.antifeatures or None,
            build_metadata=f"{config.base_url}modules/{self.id}/{self.filename(module_folder)}",
        )

    def write(self, file):
        new = AttrDict()
        keys = list(self.expected_fields().keys())

        # fields without manually
        keys.extend(["added", "last_update", "versions"])

        for key in keys:
            value = self.get(key, "")
            if value is None:
                continue

            if isinstance(value, str):
                if value == "" or value.isspace():
                    continue

            new[key] = value

        JsonIO.write(new, file)

    @classmethod
    def load(cls, file):
        obj = JsonIO.load(file)
        return TrackJson(obj)

    @classmethod
    def filename(cls, module_folder):
        pattern = r"^track\.(json|y(a)?ml)$"
        files = os.listdir(module_folder)
        for file in files:
            if re.match(pattern, file):
                return file
        raise FileNotFoundError("No matching file found in the folder. Supported file types are track.json, track.yml or track.yaml")

    @classmethod
    def expected_fields(cls, __type=True):
        if __type:
            return cls.__annotations__

        return {k: v.__name__ for k, v in cls.__annotations__.items() if v is not None and v is not False}


class TrackType(Enum):
    UNKNOWN = 0
    ONLINE_JSON = 1
    ONLINE_ZIP = 2
    GIT = 3
    LOCAL_JSON = 4
    LOCAL_ZIP = 5
    LOCAL_YAML = 6
    ONLINE_YAML = 7