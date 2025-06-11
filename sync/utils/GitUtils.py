import functools
import os
import shutil
import re
from pathlib import Path
from typing import Optional

from git import Repo, InvalidGitRepositoryError, GitCommandError, exc
from github import Github, Auth, UnknownObjectException, WorkflowRun, Artifact
from .HttpUtils import HttpUtils # Assuming this was added
from .Log import Log # Assuming this was added


class GitUtils:
    @classmethod
    @functools.lru_cache()
    def current_branch(cls, repo_dir: Path) -> Optional[str]:
        try:
            return Repo(repo_dir).active_branch.name
        except InvalidGitRepositoryError:
            return None

    @classmethod
    def _get_repo_name_from_url(cls, url: str) -> Optional[tuple[str, str]]:
        """Extracts owner and repo name from GitHub URL."""
        # Handles https://github.com/owner/repo.git and git@github.com:owner/repo.git
        match = re.match(r"(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/.]+)(?:\.git)?", url, re.IGNORECASE)
        if match:
            return match.group(1), match.group(2)
        return None

    @classmethod
    def clone_or_download_release(cls, url: str, out: Path, module_id: str, log_config: tuple, download_preference: str = "auto") -> float:
        repo_dir = out.with_suffix("")
        enable_log, log_dir_path = log_config
        logger = Log("GitUtils", enable_log=enable_log, log_dir=log_dir_path)
        api_token = os.getenv("GITHUB_TOKEN")       
        repo_parts = cls._get_repo_name_from_url(url)
        gh_instance: Optional[Github] = None
        if api_token:
            gh_instance = Github(auth=Auth.Token(api_token))

        downloaded_timestamp: Optional[float] = None

        def _try_download_from_releases() -> Optional[float]:
            if not (repo_parts and gh_instance):
                return None
            owner, repo_name = repo_parts
            logger.d(f"[{module_id}] Attempting to download from GitHub Releases: {owner}/{repo_name}")
            try:
                repo_gh = gh_instance.get_repo(f"{owner}/{repo_name}")
                releases = repo_gh.get_releases()
                if releases.totalCount > 0:
                    latest_release = releases[0]
                    logger.i(f"[{module_id}] Found latest release: {latest_release.tag_name} with {latest_release.get_assets().totalCount} asset(s)")
                    release_zip_assets = []
                    other_zip_assets = []
                    for asset_item in latest_release.get_assets():
                        if asset_item.name.endswith(".zip"):
                            if "release" in asset_item.name.lower():
                                release_zip_assets.append(asset_item)
                            else:
                                other_zip_assets.append(asset_item)
                    chosen_asset = None
                    if release_zip_assets: # 'release' を含むものを優先
                        release_zip_assets.sort(key=lambda asset: asset.updated_at, reverse=True) # Sort by updated_at in descending order
                        chosen_asset = release_zip_assets[0]
                        logger.i(f"[{module_id}] Prioritizing most recently updated 'release'-named ZIP asset: {chosen_asset.name} (updated: {chosen_asset.updated_at.isoformat()})")
                    elif other_zip_assets:
                        other_zip_assets.sort(key=lambda asset: asset.updated_at, reverse=True)
                        chosen_asset = other_zip_assets[0]
                        logger.i(f"[{module_id}] No 'release'-named ZIP asset. Selected latest other ZIP asset: {chosen_asset.name} (updated: {chosen_asset.updated_at.isoformat()})")

                    if chosen_asset:
                        logger.i(f"[{module_id}] Downloading release asset: {chosen_asset.name} from {chosen_asset.browser_download_url}")
                        HttpUtils.download(chosen_asset.browser_download_url, out) # Public releases don't need auth headers
                        return latest_release.published_at.timestamp()
                    logger.i(f"[{module_id}] No suitable .zip asset found in release {latest_release.tag_name}.")
                else:
                    logger.i(f"[{module_id}] No releases found for {owner}/{repo_name}.")
            except UnknownObjectException:
                logger.w(f"[{module_id}] Repository not found or access denied for releases: {owner}/{repo_name}.")
            except Exception as e:
                logger.w(f"[{module_id}] Error fetching GitHub release for {url}: {e}.")
            return None

        def _try_download_from_actions() -> Optional[float]:
            if not (repo_parts and gh_instance and api_token): # api_token is needed for artifact download URL
                return None
            owner, repo_name = repo_parts
            logger.d(f"[{module_id}] Attempting to download from GitHub Actions artifacts: {owner}/{repo_name}")
            try:
                repo_gh_for_actions = gh_instance.get_repo(f"{owner}/{repo_name}")
                workflow_runs = repo_gh_for_actions.get_workflow_runs(status="success")
                if workflow_runs.totalCount > 0:
                    latest_successful_run: WorkflowRun = workflow_runs[0]
                    logger.i(f"[{module_id}] Found latest successful workflow run: '{latest_successful_run.name}' (ID: {latest_successful_run.id}, triggered: {latest_successful_run.created_at.isoformat()})")
                    artifacts_list = latest_successful_run.get_artifacts()
                    if artifacts_list.totalCount > 0:
                        logger.i(f"[{module_id}] Found {artifacts_list.totalCount} artifact(s) for run {latest_successful_run.id}")
                        release_zip_artifacts = []
                        other_zip_artifacts = []
                        for artifact_item in artifacts_list: # artifact_item is Artifact
                            if not artifact_item.expired:
                                if "release" in artifact_item.name.lower():
                                    release_zip_artifacts.append(artifact_item)
                                else:
                                    other_zip_artifacts.append(artifact_item)
                        chosen_artifact: Optional[Artifact.Artifact] = None
                        if release_zip_artifacts:
                            release_zip_artifacts.sort(key=lambda art: art.updated_at, reverse=True)
                            chosen_artifact = release_zip_artifacts[0]
                            logger.i(f"[{module_id}] Prioritizing 'release'-named ZIP artifact: {chosen_artifact.name}")
                        elif other_zip_artifacts:
                            other_zip_artifacts.sort(key=lambda art: art.updated_at, reverse=True)
                            chosen_artifact = other_zip_artifacts[0]
                            logger.i(f"[{module_id}] No 'release'-named ZIP artifact. Selected latest other ZIP artifact: {chosen_artifact.name} (updated: {chosen_artifact.updated_at.isoformat()})")

                        if chosen_artifact:
                            logger.i(f"[{module_id}] Downloading artifact: {chosen_artifact.name} (ID: {chosen_artifact.id}) from {chosen_artifact.archive_download_url}")
                            dl_ts = HttpUtils.download(
                                chosen_artifact.archive_download_url,
                                out,
                                headers={"Authorization": f"Bearer {api_token}"}
                            )
                            logger.i(f"[{module_id}] Successfully downloaded artifact {chosen_artifact.name} to {out}")
                            return chosen_artifact.updated_at.timestamp() if chosen_artifact.updated_at else dl_ts
                        logger.i(f"[{module_id}] No suitable .zip artifact found in workflow run {latest_successful_run.id}.")
                    else:
                        logger.i(f"[{module_id}] No artifacts found for workflow run {latest_successful_run.id}.")
                else:
                    logger.i(f"[{module_id}] No successful workflow runs found for {owner}/{repo_name}.")
            except UnknownObjectException:
                logger.w(f"[{module_id}] Repository not found or access denied for actions: {owner}/{repo_name}.")
            except Exception as e:
                logger.w(f"[{module_id}] Error fetching GitHub Actions artifacts for {url}: {e}.")
            return None

        if gh_instance: # APIトークンがある場合のみAPI経由のダウンロードを試行
            if download_preference == "actions":
                logger.i(f"[{module_id}] Download preference: Actions first.")
                downloaded_timestamp = _try_download_from_actions()
                if downloaded_timestamp is None:
                    logger.i(f"[{module_id}] Actions download failed or not found, trying Releases.")
                    downloaded_timestamp = _try_download_from_releases()
            elif download_preference == "releases":
                logger.i(f"[{module_id}] Download preference: Releases first.")
                downloaded_timestamp = _try_download_from_releases()
                if downloaded_timestamp is None:
                    logger.i(f"[{module_id}] Releases download failed or not found, trying Actions.")
                    downloaded_timestamp = _try_download_from_actions()
            else:  # 'auto' またはその他の未定義の値の場合 (リリース優先)
                logger.i(f"[{module_id}] Download preference: Auto (Releases first, then Actions).")
                downloaded_timestamp = _try_download_from_releases()
                if downloaded_timestamp is None:
                    logger.i(f"[{module_id}] Releases download failed or not found, trying Actions.")
                    downloaded_timestamp = _try_download_from_actions()

            if downloaded_timestamp is not None:
                return downloaded_timestamp
        elif repo_parts: # APIトークンはないがGitHub URLの場合
            logger.w(f"[{module_id}] GitHub URL detected but GITHUB_API_TOKEN env var not set. Skipping API-based download, will attempt to clone.")

        # Fallback to cloning and zipping
        logger.i(f"[{module_id}] Falling back to cloning repository: {url}")
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

        try:
            repo = Repo.clone_from(url, repo_dir)
            if repo.head.is_detached:
                logger.w(f"[{module_id}] Repository HEAD is detached. Using HEAD commit for timestamp.")
                last_committed = float(repo.head.commit.committed_date)
            else:
                last_committed = float(repo.active_branch.commit.committed_date)
        except exc.GitCommandError as e:
            shutil.rmtree(repo_dir, ignore_errors=True)
            logger.e(f"[{module_id}] Clone failed for {url}: {e}")
            raise

        for path in repo_dir.iterdir():
            if path.name.startswith(".git"):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                if path.is_file():
                    path.unlink(missing_ok=True)

                continue

            os.utime(path, (last_committed, last_committed))

        archive_base_name = repo_dir.as_posix()
        try:
            shutil.make_archive(archive_base_name, format="zip", root_dir=repo_dir)
            logger.i(f"[{module_id}] Successfully created zip archive from clone: {archive_base_name}.zip")
        except FileNotFoundError:
            logger.e(f"[{module_id}] Archive creation from clone failed for {archive_base_name}")
            raise FileNotFoundError(f"archive failed: {archive_base_name}")
        finally:
            shutil.rmtree(repo_dir)
        return last_committed
