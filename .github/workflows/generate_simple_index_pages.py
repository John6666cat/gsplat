# SPDX-FileCopyrightText: Copyright 2024 the Regents of the University of California, Nerfstudio Team and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import re

import requests
from jinja2 import Template


GITHUB_REPO = os.getenv("GITHUB_REPOSITORY")
GITHUB_API_URL = os.getenv("GITHUB_API_URL", "https://api.github.com")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")

WHEEL_FILENAME_PATTERN = re.compile(
    r"^(?P<name>[\w\d_.]+)-"
    r"(?P<version>[\w\d.!+_]+)-"
    r"(?P<python_tag>[\w\d_.]+)-"
    r"(?P<abi_tag>[\w\d_.]+)-"
    r"(?P<platform_tag>[\w\d_.]+)\.whl$"
)


def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def github_get_paginated(url):
    headers = github_headers()
    params = {"per_page": 100}

    while url:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch GitHub API data: {response.status_code} {response.text}"
            )

        yield from response.json()

        url = response.links.get("next", {}).get("url")
        params = None


def parse_wheel_filename(filename):
    match = WHEEL_FILENAME_PATTERN.match(filename)
    if not match:
        raise ValueError(f"Invalid wheel filename: {filename}")

    version = match.group("version")
    local_version = None
    if "+" in version:
        _, local_version = version.split("+", 1)

    return {
        "package_name": match.group("name"),
        "local_version": local_version,
    }


def list_python_wheels():
    if not GITHUB_REPO:
        raise RuntimeError("GITHUB_REPOSITORY is not set")

    releases_url = f"{GITHUB_API_URL}/repos/{GITHUB_REPO}/releases"
    wheel_files = []

    for release in github_get_paginated(releases_url):
        for asset in release.get("assets", []):
            filename = asset["name"]
            if not filename.endswith(".whl"):
                continue

            parsed_filename = parse_wheel_filename(filename)
            wheel_files.append(
                {
                    "release_name": release.get("name") or release.get("tag_name"),
                    "wheel_name": filename,
                    "download_url": asset["browser_download_url"],
                    "package_name": parsed_filename["package_name"],
                    "local_version": parsed_filename["local_version"],
                }
            )

    return wheel_files


def generate_simple_index_htmls(wheels, outdir):
    template_versions_str = """
    <!DOCTYPE html>
    <html>
    <head><title>Python wheels links for {{ repo_name }}</title></head>
    <body>
    <h1>Python wheels for {{ repo_name }}</h1>

    {% for wheel in wheels %}
    <a href="{{ wheel.download_url }}">{{ wheel.wheel_name }}</a><br/>
    {% endfor %}

    </body>
    </html>
    """

    template_packages_str = """
    <html>
    <body>
    {% for package_name in package_names %}
        <a href="{{package_name}}/">{{package_name}}</a><br/>
    {% endfor %}
    </body>
    </html>
    """

    template_versions = Template(template_versions_str)
    template_packages = Template(template_packages_str)

    packages = {}
    for wheel in wheels:
        package_name = wheel["package_name"]
        packages.setdefault(package_name, []).append(wheel)

    html_content = template_packages.render(
        package_names=[str(k) for k in sorted(packages.keys())]
    )
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w") as file:
        file.write(html_content)

    for package_name, package_wheels in packages.items():
        html_page = template_versions.render(
            repo_name=GITHUB_REPO, wheels=package_wheels
        )
        os.makedirs(os.path.join(outdir, package_name), exist_ok=True)
        with open(os.path.join(outdir, package_name, "index.html"), "w") as file:
            file.write(html_page)


def generate_all_pages(outdir):
    wheels = list_python_wheels()
    if wheels:
        print("Python wheels found in releases:")
        for wheel in wheels:
            print(
                f"Release: {wheel['release_name']}, Wheel: {wheel['wheel_name']}, URL: {wheel['download_url']}"
            )
    else:
        print("No Python wheels found in the releases.")

    generate_simple_index_htmls(wheels, outdir=outdir)

    wheels_per_local_version = {}
    for wheel in wheels:
        local_version = wheel["local_version"]
        if local_version is None:
            continue
        wheels_per_local_version.setdefault(local_version, []).append(wheel)

    for local_version, local_version_wheels in wheels_per_local_version.items():
        generate_simple_index_htmls(
            local_version_wheels, outdir=os.path.join(outdir, local_version)
        )


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description="Generate Python Wheels Index Pages"
    )
    argparser.add_argument(
        "--outdir", help="Output directory for the index pages", default="."
    )
    args = argparser.parse_args()
    generate_all_pages(args.outdir)
