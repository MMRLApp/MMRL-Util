import json, re, os
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from sync.utils import Log

from .AttrDict import AttrDict
from .ArchiveIO import ArchiveIO
from ..error import MagiskModuleError

from .JsonIO import JsonIO

from .ModuleNote import ModuleNote
from .ModuleFeatures import ModuleFeatures
from .ModuleManager import ModuleManager
from .RootSolutions import RootSolutions

class LocalModule(AttrDict):
    id: str
    name: str
    version: str
    versionCode: int
    author: str
    description: str
    
    added: float
    timestamp: float
    size: float
    stars: int
    
    # KernelSU supported props
    metamodule: str # https://kernelsu.org/guide/metamodule.html#basic-requirements
    
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
    readme: str
    require: list[str]
    verified: bool
    note: ModuleNote
    features: ModuleFeatures
    root: RootSolutions
    manager: ModuleManager
    permissions: list[str]

    @classmethod
    def clean_json(cls, data):
        if isinstance(data, dict):
            cleaned_dict = {
                key: cls.clean_json(value)
                for key, value in data.items()
                if value not in (None, [], {}, "")
            }
            return {k: v for k, v in cleaned_dict.items() if v not in (None, [], {}, "")}
        elif isinstance(data, list):
            cleaned_list = [cls.clean_json(item) for item in data]
            return [item for item in cleaned_list if item not in (None, [], {}, "")]
        return data

    @classmethod
    def load(cls, file, track, config):    
        zip_compression = track.deep_get("options.archive.compression", default="store")
        disable_metadata = track.deep_get("options.disableRemoteMetadata", default=False)
        
        cls._log = Log("LocalModule", enable_log=config.enable_log, log_dir=config.log_dir)
        
        cls._zipfile = ArchiveIO(file=file, mode="r", compression=zip_compression)
        fields = cls.expected_fields()

        cleaned_track = cls.clean_json(track)

        if not cls._zipfile.file_exists("module.prop"):
            msg = f"'{file.name}' is not a valid Magisk module: 'module.prop' not found."
            raise MagiskModuleError(msg)

        try:
            props = cls._zipfile.file_read("module.prop")
        except Exception as err: # BaseExceptionからExceptionに変更し、エラーを連鎖させる
            msg = f"Error reading 'module.prop' from '{file}': {err}"
            raise MagiskModuleError(msg) from err

        obj = AttrDict()
        for item in props.splitlines():
            prop = item.split("=", maxsplit=1)
            if len(prop) != 2:
                continue

            key, value = prop
            if key == "" or key.startswith("#") or key not in fields:
                continue

            _type = fields[key]
            obj[key] = _type(value)

        local_module = LocalModule()
        for key in fields.keys():
            if config.allowedCategories and key == "categories" and cleaned_track.get("categories"):
                local_module[key] = JsonIO.filterArray(config.allowedCategories, cleaned_track.get(key))
            else:
                value = cleaned_track.get(key) if cleaned_track.get(key) is not None else obj.get(key)
                if value is not None and value is not False:
                    local_module[key] = value

        try:
            if not disable_metadata:                
                meta_file = cls.get_repo_json()

                if meta_file is not None:
                    cls._log.i(f"load: [{track.id}] -> found {meta_file}")
                    try:
                        _, ext = os.path.splitext(meta_file)
                        
                        match ext.lower():
                            case ".json":
                                raw_content = cls._zipfile.file_read(meta_file)
                                cls._log.d(f"load: [{track.id}] -> JSON content length: {len(raw_content)}")
                                raw_json = json.loads(raw_content)
                            case ".yaml" | ".yml":
                                if not YAML_AVAILABLE:
                                    cls._log.e(f"load: [{track.id}] -> YAML support not available, install PyYAML")
                                    raw_json = None
                                else:
                                    raw_content = cls._zipfile.file_read(meta_file)
                                    cls._log.d(f"load: [{track.id}] -> YAML content length: {len(raw_content)}")
                                    raw_json = yaml.load(raw_content, Loader=yaml.FullLoader)
                            case _:
                                cls._log.w(f"load: [{track.id}] -> unsupported metadata file extension: {ext}")
                                raw_json = None
                        
                        if raw_json is not None:
                            cls._log.d(f"load: [{track.id}] -> parsed metadata keys: {list(raw_json.keys())}")
                            raw_json = cls.clean_json(raw_json)
                            cls._log.d(f"load: [{track.id}] -> cleaned metadata keys: {list(raw_json.keys())}")
                        
                    except json.JSONDecodeError as e:
                        cls._log.e(f"load: [{track.id}] -> failed to parse JSON from {meta_file}: {e}")
                        raw_json = None
                    except Exception as e:
                        # This will catch yaml.YAMLError if yaml is available, or any other parsing error
                        if YAML_AVAILABLE and 'yaml' in str(type(e)).lower():
                            cls._log.e(f"load: [{track.id}] -> failed to parse YAML from {meta_file}: {e}")
                        else:
                            cls._log.e(f"load: [{track.id}] -> error reading {meta_file}: {e}")
                        raw_json = None
                else:
                    cls._log.d(f"load: [{track.id}] -> no repo metadata file found")
                    raw_json = None

                if raw_json is not None:
                    for item in raw_json.items():
                        key, value = item
                        
                        # Only process keys that are valid fields in the class
                        if key in fields:
                            try:
                                _type = fields[key]
                                typed_value = _type(value)
                                if typed_value is not None and typed_value is not False:
                                    local_module[key] = typed_value
                            except (ValueError, TypeError) as e:
                                cls._log.w(f"load: [{track.id}] -> failed to convert {key}={value} to {_type}: {e}")
                                continue
            else:
                cls._log.w(f"load: [{track.id}] -> remote metadata disabled")
                    
        except Exception as e:
            cls._log.e(f"load: [{track.id}] -> error processing repo metadata: {e}")
            # Continue with processing even if metadata fails

        local_module.verified = track.verified or False
        local_module.added = track.added or 0
        local_module.timestamp = track.last_update
        local_module.size = Path(file).stat().st_size
        local_module.permissions = []     
        
        webui_config_file = cls.get_webui_config()
        if webui_config_file is not None:
            cls._log.i(f"load: [{track.id}] -> found {webui_config_file}")
            config_raw_json = json.loads(cls._zipfile.file_read(webui_config_file))
            local_module.permissions = config_raw_json.get("permissions", [])

        if cls._zipfile.file_exists(f"service.sh") or cls._zipfile.file_exists(f"common/service.sh"):
            local_module.permissions.append("magisk.permission.SERVICE")

        if cls._zipfile.file_exists(f"post-fs-data.sh") or cls._zipfile.file_exists(f"common/post-fs-data.sh"):
            local_module.permissions.append("magisk.permission.POST_FS_DATA")
            
        if cls._zipfile.file_exists(f"system.prop") or cls._zipfile.file_exists(f"common/system.prop"):
            local_module.permissions.append("magisk.permission.RESETPROP")
            
        if cls._zipfile.file_exists(f"sepolicy.rule"):
            local_module.permissions.append("magisk.permission.SEPOLICY")
            
        if cls._zipfile.file_exists(f"zygisk/"):
            local_module.permissions.append("magisk.permission.ZYGISK")
            
        if cls._zipfile.file_exists(f"action.sh") or cls._zipfile.file_exists(f"common/action.sh"):
            local_module.permissions.append("magisk.permission.ACTION")
            
        if cls._zipfile.file_exists(f"webroot/index.html"):
            local_module.permissions.append("kernelsu.permission.WEBUI")
        
        if cls._zipfile.file_exists(f"webroot/index.mmrl.html") or cls._zipfile.file_exists(f"webroot/index.wx.html"):
            local_module.permissions.append("mmrl.permission.WEBUI")
            
        if cls._zipfile.file_exists(f"webroot/config.mmrl.json") or cls._zipfile.file_exists(f"webroot/config.json"):
            local_module.permissions.append("mmrl.permission.WEBUI_CONFIG")
        
        if cls._zipfile.file_exists(f"post-mount.sh") or cls._zipfile.file_exists(f"common/post-mount.sh"):
            local_module.permissions.append("kernelsu.permission.POST_MOUNT")
            
        if cls._zipfile.file_exists(f"boot-completed.sh") or cls._zipfile.file_exists(f"common/boot-completed.sh"):
            local_module.permissions.append("kernelsu.permission.BOOT_COMPLETED")
        
        if len([name for name in cls._zipfile.namelist() if name.endswith('.apk')]) != 0:
            local_module.permissions.append("mmrl.permission.APKS")

        if len([name for name in cls._zipfile.namelist() if name.endswith('.dex')]) != 0:
            local_module.permissions.append("mmrl.permission.DEXS")

        if local_module.get("metamodule") in [1, True, "true", "True"]:
            local_module.permissions.append("kernelsu.permission.METAMODULE")
        
        features = {
            "service": cls._zipfile.file_exists(f"service.sh") or cls._zipfile.file_exists(f"common/service.sh"),
            "post_fs_data": cls._zipfile.file_exists(f"post-fs-data.sh") or cls._zipfile.file_exists(f"common/post-fs-data.sh"),
            # system.prop
            "resetprop": cls._zipfile.file_exists(f"system.prop") or cls._zipfile.file_exists(f"common/system.prop"),
            "sepolicy": cls._zipfile.file_exists(f"sepolicy.rule"),
            
            "zygisk": cls._zipfile.file_exists(f"zygisk/"),
            "action": cls._zipfile.file_exists(f"action.sh") or cls._zipfile.file_exists(f"common/action.sh"),
            
            # KernelSU
            "webroot": cls._zipfile.file_exists(f"webroot/index.html"),
            "post_mount": cls._zipfile.file_exists(f"post-mount.sh") or cls._zipfile.file_exists(f"common/post-mount.sh"),
            "boot_completed": cls._zipfile.file_exists(f"boot-completed.sh") or cls._zipfile.file_exists(f"common/boot-completed.sh"),

            # MMRL
            "modconf": cls._zipfile.file_exists(f"system/usr/share/mmrl/config/{local_module.id}/index.jsx"),
            
            "apks": len([name for name in cls._zipfile.namelist() if name.endswith('.apk')]) != 0
        }
        
        local_module.features = {k: v for k, v in features.items() if v is not None and v is not False}

        return cls.clean_json(local_module)
   
    @classmethod
    def get_repo_json(cls):
        pattern = r"^common\/repo\.(json|y(a)?ml)$"
        files = cls._zipfile.namelist()
        
        # Debug: log all files that start with 'common'
        common_files = [f for f in files if f.lower().startswith('common')]
        if common_files:
            cls._log.d(f"get_repo_json: found common files: {common_files}")
        
        for file in files:
            # Normalize path separators for comparison
            normalized_file = file.replace('\\', '/')
            if re.match(r"^common\/repo\.(json|y(a)?ml)$", normalized_file):
                cls._log.d(f"get_repo_json: matched repo file: {file}")
                return file
                
        cls._log.d(f"get_repo_json: no repo file found matching pattern {pattern}")
        return None
    
    @classmethod
    def get_webui_config(cls):
        files = cls._zipfile.namelist()
        
        for file in files:
            # Normalize path separators for comparison
            normalized_file = file.replace('\\', '/')
            if re.match(r"^webroot\/config\.mmrl\.(json|y(a)?ml)$", normalized_file):
                cls._log.d(f"get_webui_config: matched config file: {file}")
                return file
                
        return None
   
    @classmethod
    def expected_fields(cls, __type=True):
        if __type:
            return cls.__annotations__

        return {k: v.__name__ for k, v in cls.__annotations__.items() if v is not None and v is not False}

