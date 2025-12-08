from datetime import datetime
import os

from git import Repo
from tabulate import tabulate

from .Config import Config
from ..error import Result
from ..model import (
    AttrDict,
    ModulesJson,
    UpdateJson,
    LocalModule,
    OnlineModule
)
from ..track import LocalTracks
from ..utils import Log, GitHubGraphQLAPI, GitUtils


class Index:
    versions = [0, 1]
    latest_version = versions[-1]

    def __init__(self, root_folder, config):
        self._log = Log("Index", enable_log=config.enable_log, log_dir=config.log_dir)
        self._root_folder = root_folder

        self._modules_folder = Config.get_modules_folder(root_folder)
        self._tracks = LocalTracks(self._modules_folder, config)
        self._config = config

        self._json_folder = Config.get_json_folder(root_folder)
        
        # Initialize GitHub API if token is available
        api_token = os.getenv("GITHUB_TOKEN")
        self._github_api = GitHubGraphQLAPI(api_token) if api_token else None

        # noinspection PyTypeChecker
        self.modules_json = None

    def _add_modules_json_0(self, track, update_json, online_module):
        if self.modules_json is None:
            self.modules_json = ModulesJson(
                name=self._config.name,
                timestamp=datetime.now().timestamp(),
                modules=list()
            )

        latest_item = update_json.versions[-1]

        online_module.license = track.license or ""
        online_module.states = AttrDict(
            zipUrl=latest_item.zipUrl,
            changelog=latest_item.changelog
        )

        self.modules_json.modules.append(online_module)

    def _add_modules_json_1(self, track, update_json, online_module):
        if self.modules_json is None:
            self.modules_json = ModulesJson(
                id=self._config.id,
                name=self._config.name,
                website=self._config.website,
                support=self._config.support,
                donate=self._config.donate,
                submission=self._config.submission,
                cover=self._config.cover,
                description=self._config.description,
                metadata=AttrDict(
                    version=1,
                    timestamp=datetime.now().timestamp()
                ),
                modules=list()
            )

        module_folder = self._modules_folder.joinpath(track.id)
        online_module.track = track.json(self._config, module_folder)
        online_module.versions = update_json.versions

        self.modules_json.modules.append(online_module)

    def _add_modules_json(self, track, update_json, online_module, version):
        if version not in self.versions:
            raise RuntimeError(f"unsupported version: {version}")

        func = getattr(self, f"_add_modules_json_{version}")
        func(
            track=track,
            update_json=update_json,
            online_module=online_module,
        )

    def get_online_module(self, track, zip_file):
        @Result.catching()
        def get_online_module():
            local_module = LocalModule.load(zip_file, track, self._config)
            online_module = OnlineModule.from_dict(local_module)
            
            # Try to fetch GitHub stars if source is a valid GitHub URL
            if self._github_api and track.source:
                repo_info = GitUtils.get_repo_name_from_url(track.source)
                if repo_info:
                    owner, repo = repo_info
                    try:
                        stars = self._github_api.get_stargazers_count(owner, repo)
                        if stars is not None:
                            online_module.stars = stars
                            self._log.d(f"get_online_module: [{track.id}] -> fetched {stars} stars from {owner}/{repo}")
                    except Exception as e:
                        self._log.w(f"get_online_module: [{track.id}] -> failed to fetch stars: {e}")
            
            return online_module

        result = get_online_module()
        if result.is_failure:
            msg = Log.get_msg(result.error)
            self._log.e(f"get_online_module: [{track.id}] -> {msg}")
            return None

        else:
            return result.value

    def __call__(self, version, to_file):
        for track in self._tracks.get_tracks():
            module_folder = self._modules_folder.joinpath(track.id)
            update_json_file = module_folder.joinpath(UpdateJson.filename())
            if not update_json_file.exists():
                continue

            update_json = UpdateJson.load(update_json_file)
            latest_item = update_json.versions[-1]

            zip_file = module_folder.joinpath(latest_item.zipfile_name)
            if not zip_file.exists():
                continue

            online_module = self.get_online_module(track, zip_file)
            if online_module is None:
                continue

            self._add_modules_json(
                track=track,
                update_json=update_json,
                online_module=online_module,
                version=version
            )

        self.modules_json.modules.sort(key=lambda v: v.id)
        if to_file:
            json_file = self._json_folder.joinpath(ModulesJson.filename())
            self.modules_json.write(json_file)

        return self.modules_json

    def push_by_git(self, branch):
        json_file = self._json_folder.joinpath(ModulesJson.filename())
        timestamp = ModulesJson.load(json_file).get_timestamp()
        msg = f"Update by CLI ({datetime.fromtimestamp(timestamp)})"

        repo = Repo(self._root_folder)
        repo.git.add(all=True)
        repo.index.commit(msg)
        repo.remote().push(branch)

    def get_versions_table(self):
        headers = ["id", "name", "latest version"]
        table = []

        for track in self._tracks.get_tracks():
            module_folder = self._modules_folder.joinpath(track.id)
            update_json_file = module_folder.joinpath(UpdateJson.filename())

            if not update_json_file.exists():
                table.append(
                    [track.id, "-", "-"]
                )
                continue

            update_json = UpdateJson.load(update_json_file)
            latest = update_json.versions[-1]
            zip_file = module_folder.joinpath(latest.zipfile_name)
            online_module = self.get_online_module(track, zip_file)

            if online_module is not None:
                name = online_module.name.replace("|", "-")
                table.append(
                    [online_module.id, name, online_module.version_display]
                )
            else:
                table.append(
                    [track.id, "-", "-"]
                )

        markdown_text = tabulate(table, headers, tablefmt="github")
        return markdown_text
