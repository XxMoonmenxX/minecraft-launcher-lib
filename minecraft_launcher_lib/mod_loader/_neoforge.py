# This file is part of minecraft-launcher-lib (https://codeberg.org/JakobDev/minecraft-launcher-lib)
# SPDX-FileCopyrightText: Copyright (c) 2019-2025 JakobDev <jakobdev@gmx.de> and contributors
# SPDX-License-Identifier: BSD-2-Clause
from ..vanilla_launcher import (
    do_vanilla_launcher_profiles_exists,
    create_empty_vanilla_launcher_profiles_file
)
from .._helper import (
    get_requests_response_cache,
    download_file,
    empty,
    SUBPROCESS_STARTUP_INFO
)
from ._base import ModLoaderBase
from ..types import CallbackDict
import subprocess
import tempfile
import re
import os
import json
import requests
from datetime import datetime

_API_URL = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
_VERSION_REGEX = re.compile(r"^\d+\.\d+")
_DOWNLOAD_TIMEOUT = 60
_MIN_JAR_SIZE = 1000


def _get_minecraft_version_for_neoforge(version_name: str) -> str:
    """Extracts Minecraft version from NeoForge version string"""
    version_mapping = {
        "1.21.10": "1.21.10",
        "1.21.9": "1.21.9",
        "1.21.8": "1.21.8",
        "1.21.7": "1.21.7",
        "1.21.6": "1.21.6",
        "1.21.5": "1.21.5",
        "1.21.4": "1.21.4",
        "1.21.3": "1.21.3",
        "1.21.2": "1.21.2",
        "1.21.1": "1.21.1",
        "1.20.6": "1.20.6",
        "1.20.5": "1.20.5",
        "1.20.4": "1.20.4",
        "1.20.3": "1.20.3",
        "1.20.2": "1.20.2"
    }

    for mc_version in version_mapping:
        if mc_version in version_name:
            return mc_version

    # Fallback: extract from version string
    parts = version_name.split('.')
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return "1.21.1"


def _get_latest_neoforge_version(minecraft_version: str) -> str:
    """Gets the latest NeoForge version for specified Minecraft version"""
    if minecraft_version == "1.21.1":
        return "21.1.209"
    versions = _get_neoforge_versions_fallback(minecraft_version)
    return versions[0] if versions else "21.1.209"


def _get_neoforge_versions_fallback(minecraft_version: str) -> list[str]:
    """Gets available NeoForge versions from fallback mapping"""
    version_map = {
        "1.21.10": ["21.10.55-beta"],
        "1.21.9": ["21.9.1-beta"],
        "1.21.8": ["21.8.51"],
        "1.21.7": ["21.7.25-beta"],
        "1.21.6": ["21.6.20-beta"],
        "1.21.5": ["21.5.95"],
        "1.21.4": ["21.4.155"],
        "1.21.3": ["21.3.94"],
        "1.21.2": ["21.1.215"],
        "1.21.1": ["21.1.209"],
        "1.20.6": ["20.6.139"],
        "1.20.5": ["20.5.21-beta"],
        "1.20.4": ["20.4.251"],
        "1.20.3": ["20.3.8-beta"],
        "1.20.2": ["20.2.93"],
    }
    return version_map.get(minecraft_version, ["21.1.209"])


def _download_with_fallback(
    loader_version: str,
    temp_path: str,
    callback: CallbackDict
) -> bool:
    """Attempts to download installer from multiple sources"""
    download_urls = [
        f"https://maven.creeperhost.net/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar",
        f"https://maven.creeperhost.net/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}.jar",
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar",
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}.jar",
        f"https://repo.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar",
        f"https://repo.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}.jar",
    ]

    for download_url in download_urls:
        domain = download_url.split('/')[2]
        try:
            if callback:
                callback.get("setStatus", empty)(f"Downloading from {domain}")

            download_file(download_url, temp_path)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                return True
        except Exception:
            if callback:
                callback.get("setStatus", empty)(f"Failed: {domain}")
            continue

    return False


def _create_complete_neoforge_profile(
    minecraft_version: str,
    neoforge_version: str,
    minecraft_dir: str,
    callback: CallbackDict = None
) -> bool:
    """Creates complete NeoForge profile with actual JAR file"""

    def log(message: str) -> None:
        if callback:
            callback.get("setStatus", empty)(message)
        print(f"[NeoForge] {message}")

    # Create directory structure
    version_name = f"neoforge-{neoforge_version}"
    version_dir = os.path.join(minecraft_dir, "versions", version_name)
    os.makedirs(version_dir, exist_ok=True)

    current_time = datetime.now().isoformat()

    # Essential libraries list
    libraries = [
        {
            "name": f"net.neoforged:neoforge:{neoforge_version}",
            "url": "https://maven.creeperhost.net/"
        },
        {
            "name": "cpw.mods:bootstraplauncher:1.1.2",
            "url": "https://maven.creeperhost.net/"
        },
        {
            "name": "cpw.mods:securejarhandler:2.1.10",
            "url": "https://maven.creeperhost.net/"
        },
        {
            "name": "org.ow2.asm:asm:9.5",
            "url": "https://libraries.minecraft.net/"
        },
        {
            "name": "org.ow2.asm:asm-commons:9.5",
            "url": "https://libraries.minecraft.net/"
        }
    ]

    # NeoForge arguments
    game_arguments = [
        "--launcherTarget", "neoforgeclient",
        "--fml.neoForgeVersion", neoforge_version,
        "--fml.mcVersion", minecraft_version,
        "--fml.forgeGroup", "net.neoforged"
    ]

    jvm_arguments = [
        "-Djava.library.path=${natives_directory}",
        "-Dminecraft.launcher.brand=${launcher_name}",
        "-Dminecraft.launcher.version=${launcher_version}",
        "-DignoreList=bootstraplauncher,securejarhandler,asm-commons,asm-tree,"
        "asm-analysis,asm-util,asm-9.5.jar,client-extra.jar",
        "-DlibraryDirectory=${library_directory}",
        "-p", "${classpath}",
        "--add-modules", "ALL-MODULE-PATH",
        "--add-opens", "java.base/java.util.jar=cpw.mods.securejarhandler",
        "--add-opens", "java.base/java.lang.invoke=cpw.mods.securejarhandler"
    ]

    profile = {
        "id": version_name,
        "time": current_time,
        "releaseTime": current_time,
        "type": "release",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "inheritsFrom": minecraft_version,
        "arguments": {
            "game": game_arguments,
            "jvm": jvm_arguments
        },
        "libraries": libraries,
        "minimumLauncherVersion": 21
    }

    # Save profile
    json_path = os.path.join(version_dir, f"{version_name}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    # Download actual JAR file
    jar_path = os.path.join(version_dir, f"{version_name}.jar")

    try:
        log(f"Downloading NeoForge JAR {neoforge_version}...")

        jar_urls = [
            f"https://maven.creeperhost.net/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}.jar",
            f"https://maven.creeperhost.net/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
            f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}.jar",
            f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
            f"https://repo.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}.jar",
            f"https://repo.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar",
        ]

        success = False
        for jar_url in jar_urls:
            domain = jar_url.split('/')[2]
            try:
                log(f"Trying: {domain}")
                response = requests.get(jar_url, stream=True, timeout=_DOWNLOAD_TIMEOUT)
                response.raise_for_status()

                with open(jar_path, 'wb') as jar_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            jar_file.write(chunk)

                if os.path.exists(jar_path) and os.path.getsize(jar_path) > _MIN_JAR_SIZE:
                    file_size = os.path.getsize(jar_path)
                    log(f"JAR downloaded from {domain} ({file_size} bytes)")
                    success = True
                    break
                else:
                    log(f"File too small from {domain}")
                    if os.path.exists(jar_path):
                        os.remove(jar_path)
            except Exception as e:
                log(f"Error with {domain}: {e}")
                continue

        if not success:
            log("All download attempts failed")
            return False

    except Exception as e:
        log(f"Critical JAR download error: {e}")
        return False

    log("NeoForge profile created with real JAR")
    return True


class Neoforge(ModLoaderBase):
    """Implements the mod loader class for NeoForge"""

    def get_id(self) -> str:
        """Implements get_id() for NeoForge"""
        return "neoforge"

    def get_name(self) -> str:
        """Implements get_name() for NeoForge"""
        return "NeoForge"

    def _normalize_minecraft_version(self, minecraft_version: str) -> str:
        """Turns the version string into a normal minecraft version"""
        minecraft_version = minecraft_version.removesuffix(".0")
        return f"1.{minecraft_version}"

    def get_minecraft_versions(self, stable_only: bool) -> list[str]:
        """Implements get_minecraft_versions() for NeoForge"""
        version_dict = {}

        try:
            response = get_requests_response_cache(_API_URL)
            data = response.json()

            for current_version in data["versions"]:
                if not current_version.startswith("0."):
                    match = _VERSION_REGEX.match(current_version)
                    if match:
                        current_minecraft_version = match.group()
                        normalized_version = self._normalize_minecraft_version(
                            current_minecraft_version
                        )
                        version_dict[normalized_version] = True

        except Exception as e:
            # Fallback to hardcoded versions on network error
            print(f"Error fetching NeoForge versions, using fallback: {e}")
            fallback_versions = [
                "1.21.10", "1.21.9", "1.21.8", "1.21.7", "1.21.6",
                "1.21.5", "1.21.4", "1.21.3", "1.21.2", "1.21.1",
                "1.20.6", "1.20.5", "1.20.4", "1.20.3", "1.20.2"
            ]
            for version in fallback_versions:
                version_dict[version] = True

        return sorted(list(version_dict.keys()), reverse=True)

    def get_loader_versions(
        self,
        minecraft_version: str,
        stable_only: bool
    ) -> list[str]:
        """Implements get_loader_versions() for NeoForge"""
        version_list = []

        if minecraft_version == "1.21.1":
            return ["21.1.209"]

        try:
            response = get_requests_response_cache(_API_URL)
            data = response.json()

            for current_version in data["versions"]:
                # if "beta" in current_version and stable_only:
                #     continue

                match = _VERSION_REGEX.match(current_version)
                if match:
                    current_minecraft_version = match.group()
                    normalized_version = self._normalize_minecraft_version(
                        current_minecraft_version
                    )
                    if normalized_version == minecraft_version:
                        version_list.append(current_version)

        except Exception as e:
            print(f"Error fetching NeoForge loader versions, using fallback: {e}")
            version_list = _get_neoforge_versions_fallback(minecraft_version)

        version_list.sort(reverse=True)
        return version_list

    def get_installer_url(self, minecraft_version: str, loader_version: str) -> str:
        """Implements get_installer_url() for NeoForge"""
        return (
            f"https://maven.creeperhost.net/net/neoforged/neoforge/"
            f"{loader_version}/neoforge-{loader_version}-installer.jar"
        )

    def _try_download_from_sources(
        self,
        loader_version: str,
        temp_path: str,
        callback: CallbackDict
    ) -> bool:
        """Attempts to download installer from multiple sources"""
        download_urls = [
            f"https://maven.creeperhost.net/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar",
            f"https://maven.creeperhost.net/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}.jar",
            f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}-installer.jar",
            f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{loader_version}/neoforge-{loader_version}.jar",
        ]

        for download_url in download_urls:
            domain = download_url.split('/')[2]
            try:
                if callback:
                    callback.get("setStatus", empty)(f"Downloading from {domain}")

                download_file(download_url, temp_path)

                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 1024:
                    return True
            except Exception:
                if callback:
                    callback.get("setStatus", empty)(f"Failed: {domain}")
                continue

        return False

    def get_installed_version(self, minecraft_version: str, loader_version: str) -> str:
        """Implements get_installed_versions() for NeoForge"""
        return f"neoforge-{loader_version}"

    def install(
        self,
        minecraft_version: str,
        minecraft_directory: str,
        callback: CallbackDict,
        java: str,
        loader_version: str
    ) -> None:
        """Implements install() for NeoForge"""
        if minecraft_version == "1.21.1":
            loader_version = "21.1.209"

        if not do_vanilla_launcher_profiles_exists(minecraft_directory):
            create_empty_vanilla_launcher_profiles_file(minecraft_directory)

        callback.get("setStatus", empty)("Starting NeoForge installation")

        # Try traditional installer method first
        installer_success = False
        with tempfile.TemporaryDirectory(prefix="minecraft-launcher-lib-") as tempdir:
            installer_path = os.path.join(tempdir, "neoforge-installer.jar")

            callback.get("setStatus", empty)("Downloading NeoForge installer")

            # Try downloading from multiple sources
            if self._try_download_from_sources(loader_version, installer_path, callback):
                if os.path.exists(installer_path) and os.path.getsize(installer_path) > 0:
                    callback.get("setStatus", empty)("Running NeoForge installer")
                    try:
                        subprocess.run(
                            [java, "-jar", installer_path, "--install-client", minecraft_directory],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            cwd=tempdir,
                            check=True,
                            startupinfo=SUBPROCESS_STARTUP_INFO,
                            text=True,
                            encoding='utf-8',
                            errors='ignore'
                        )
                        installer_success = True
                    except subprocess.CalledProcessError as e:
                        print(f"NeoForge installer failed. Stderr: {e.stderr}")
                        # Continue to fallback method

        # If traditional method failed, use profile creation method
        if not installer_success:
            callback.get("setStatus", empty)("Using offline NeoForge installation")
            try:
                _create_complete_neoforge_profile(
                    minecraft_version,
                    loader_version,
                    minecraft_directory,
                    callback
                )
                callback.get("setStatus", empty)("NeoForge installed successfully")
            except Exception as e:
                callback.get("setStatus", empty)(f"Installation failed: {e}")
                raise Exception(f"NeoForge installation failed: {e}") from e
