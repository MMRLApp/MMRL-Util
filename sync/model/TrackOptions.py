from .AttrDict import AttrDict

class TrackOptionsArchive(AttrDict):
    compression: str

    @classmethod
    def expected_fields(cls, __type=True):
        if __type:
            return cls.__annotations__

        return {k: v.__name__ for k, v in cls.__annotations__.items()}

class TrackOptions(AttrDict):
    archive: TrackOptionsArchive
    disableRemoteMetadata: bool
    
    @classmethod
    def expected_fields(cls, __type=True):
        if __type:
            return cls.__annotations__

        return {k: v.__name__ for k, v in cls.__annotations__.items()}