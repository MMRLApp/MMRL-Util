import json
import yaml
import os
import re

from sync.model.AttrDict import AttrDict

def represent_attr_dict(dumper: yaml.Dumper, value: AttrDict):
    return dumper.represent_mapping('tag:yaml.org,2002:map', value.items())

yaml.add_representer(AttrDict, represent_attr_dict, Dumper=yaml.SafeDumper)

class JsonIO:
    def write(self, file):
        assert isinstance(self, dict)

        _, ext = os.path.splitext(file)

        file.parent.mkdir(parents=True, exist_ok=True)

        match ext.lower():
            case ".json":
                with open(file, "w") as f:
                    json.dump(self, f, indent=2)
            case ".yaml" | ".yml":
                with open(file, "w") as f: 
                    yaml.dump(dict(self), f, indent=2, default_flow_style=False, Dumper=yaml.SafeDumper)
            case _:
                raise ValueError(f"Invalid file extension: {file}")

    @classmethod
    def filter(cls, text):
        return re.sub(r",(?=\s*?[}\]])", "", text)

    @classmethod
    def filterArray(cls, filter, toFilter):
        return [i for i in filter if i in toFilter]
 
    @classmethod
    def load(cls, file):
        
        _, ext = os.path.splitext(file)
        
        match ext.lower():
            case ".json":
                with open(file, encoding="utf-8", mode="r") as f:
                    text = cls.filter(f.read())
                    obj = json.loads(text)
            case ".yaml" | ".yml":
                with open(file, encoding="utf-8", mode="r") as f:
                    text = cls.filter(f.read())
                    obj = yaml.load(text, Loader=yaml.FullLoader)
            case _:
                raise ValueError(f"Invalid file extension: {file}")
        
        assert isinstance(obj, dict)
        return obj