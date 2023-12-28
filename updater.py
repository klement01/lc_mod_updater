"""
Collects Lethal Company mods from Thunderstore (thunderstore.io).
"""

# pylint: disable=logging-fstring-interpolation

import argparse
import bs4
import dataclasses
import datetime
import logging
import os
import pathlib
import re
import requests
import shutil
import sys
import urllib.parse
import zipfile

DOMAIN = "thunderstore.io"
DOMAIN_SCHEMA = f"https://{DOMAIN}"

LV1_FOLDER_NAME = "BepInEx"
LVL1_FOLDER = pathlib.Path(LV1_FOLDER_NAME)
LVL2_FOLDER_NAMES = ["cache", "config", "core", "patchers", "plugins"]
LVL2_FOLDERS = [pathlib.Path(p) for p in LVL2_FOLDER_NAMES]


@dataclasses.dataclass
class ModListing:
    """Data about a mod."""

    name: str
    url: str
    last_updated: datetime.date
    version: str
    download: str
    dependencies: [str]

    def full_id(self) -> str:
        """Returns the full identification of the mod in string format."""
        return f"{self.name}_{self.last_updated.isoformat()}_{self.version}"


@dataclasses.dataclass
class Patch:
    """Data about a game patch."""

    date: datetime.date
    title: str | None


def __main():
    """Collects settings from command line arguments."""
    today = datetime.date.today()
    time_now = datetime.datetime.now()
    time_stamp = time_now.strftime("%Y-%m-%d_%H-%M-%S")

    parser = argparse.ArgumentParser(
        prog="Lethal Company Mod Updater",
        description="Downloads latest versions of provided mods from thunderstore.io",
    )

    parser.add_argument(
        "mod_list_file",
        type=pathlib.Path,
        help="File with mod URLs between brackets: <thunderstore.io/package/...>",
    )
    parser.add_argument(
        "-e",
        "--export",
        nargs="?",
        type=pathlib.Path,
        const=pathlib.Path(f"LC_modlist_{time_stamp}.txt"),
        help="Export formatted mod list from acquired data",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Enable verbose logging.
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Extract all URLs from file.
    urls = get_urls_from_file(args.mod_list_file)

    # Assert any URL has been found.
    if len(urls) == 0:
        exit_failure("No URLs found in file")

    # Check if all URLs are from the correct domain.
    for url in urls:
        if urllib.parse.urlparse(url).netloc != DOMAIN:
            exit_failure(f"URL not from {DOMAIN}: {url}")

    # Collect mod data.
    original_mods, dependencies = collect_mod_data(urls)

    # Export formatted mod list, if requested.
    if args.export:
        export_mod_list(args.export, original_mods)

    # Shows last update time (from oldest to newest)
    for mod in sorted(original_mods, key=lambda m: m.last_updated):
        last_updated = mod.last_updated
        delta = (today - last_updated).days
        print(
            f"{mod.name}: updated {delta} day(s) ago ({last_updated.isoformat()}, "
            f"version {mod.version}, <{mod.url}>)"
        )

    # Download all mods.
    all_mods = original_mods[::]
    all_mods.extend(dependencies)

    mod_paths = []
    for mod in all_mods:
        mod_path = download_mod_from_listing(mod)
        mod_paths.append(mod_path)

    # Create base file tree.
    base_path = pathlib.Path(f"LC_modpack_{time_stamp}")
    create_modpack_tree(base_path)

    # Extract mods (dependencies first).
    for mod_path in reversed(mod_paths):
        extract_mod(base_path, mod_path)


def create_modpack_tree(base_path: pathlib.Path):
    """Create the basic tree for the mods."""
    logging.info(f"Creating tree at: {base_path}")
    try:
        os.mkdir(base_path)
    except FileExistsError:
        exit_failure(f"Folder {base_path} already exists")

    os.mkdir(base_path / LVL1_FOLDER)
    for lvl2_folder in LVL2_FOLDERS:
        os.mkdir(base_path / LVL1_FOLDER / lvl2_folder)


def extract_mod(base_path: pathlib.Path, mod_path: pathlib.Path):
    """Tries extracting the mod to the correct place in the base tree."""
    logging.info(f"Verifying: {mod_path}")
    file = zipfile.ZipFile(mod_path)
    contents = [
        c
        for c in file.namelist()
        if c not in ["icon.png", "manifest.json", "README.md", "CHANGELOG.md"]
    ]
    paths = [pathlib.Path(c) for c in contents]

    # Determines where to extract files.
    is_bepinex = False
    if any(path.parts[0] == "BepInExPack" for path in paths):
        # Mod is BepInEx.
        is_bepinex = True
        extract_path = base_path
    elif any(path.parts[0].lower() == LV1_FOLDER_NAME.lower() for path in paths):
        # Mod should be placed in root.
        extract_path = base_path
    elif any(
        path.parts[0].lower() in [f.lower() for f in LVL2_FOLDER_NAMES]
        for path in paths
    ):
        # Mod should be placed in BepInEx folder.
        extract_path = base_path / pathlib.Path("BepInEx")
    else:
        # Mod should be placed in BepInEx/plugins
        extract_path = base_path / pathlib.Path("BepInEx/plugins")

    logging.info(f"Unpacking: {mod_path}")
    for content in contents:
        file.extract(content, extract_path)
    if is_bepinex:
        logging.info(f"BepInEx detected: {mod_path}")
        pack_path = extract_path / pathlib.Path("BepInExPack")
        shutil.copytree(pack_path, extract_path, dirs_exist_ok=True)
        shutil.rmtree(pack_path)

    file.close()


def get_urls_from_file(file: pathlib.Path) -> [str]:
    """Returns URLs between brackets (e.g. <example.com>) from file."""
    logging.info(f"Reading: {file}")

    with open(file, encoding="utf-8") as f:
        urls = re.findall("<([^>]+)>", f.read())

    logging.info(f"Found {len(urls)} URLs")

    return urls


def export_mod_list(file: pathlib.Path, listings: [ModListing]):
    """Saves mod information as a formatted file."""
    logging.info(f"Exporting mod list for {len(listings)} mod(s)")

    with open(file, encoding="utf-8", mode="w") as f:
        for listing in sorted(listings, key=lambda m: m.name):
            name = listing.name
            url = listing.url
            line = f"{name}\n<{url}>\n\n"
            f.write(line)


def download_mod_from_listing(mod: ModListing) -> pathlib.Path:
    """Download mod from ModListing using given URL and data, return path."""
    path = pathlib.Path(f"{mod.full_id()}.zip")
    if path.is_file():
        logging.info(f"Skipping download, archive found at: {path}")
        return path

    logging.info(f"Downloading mod: {mod.name}")
    file = get_data_from_url(mod.download)

    logging.info(f"Saving mod {mod.name} as {path}")
    with open(path, mode="wb") as f:
        for chunk in file.iter_content(chunk_size=1024):
            f.write(chunk)

    return path


def collect_mod_data(urls: [str]) -> ([ModListing], [ModListing]):
    """Gets data for all mods pointed by the URL list and their dependencies."""
    logging.info(f"Collecting mod data from {len(urls)} URL(s)")

    listings = []

    urls = set(urls)
    new_urls = urls

    while True:
        new_listings = [get_mod_listing(url) for url in new_urls]
        listings.extend(new_listings)

        new_urls = set(dep for listing in new_listings for dep in listing.dependencies)
        new_urls.difference_update(urls)

        # All dependencies have been gotten.
        if len(new_urls) == 0:
            logging.info("No more dependencies found")
            break

        logging.info(f"New dependencies found: <{'>, <'.join(new_urls)}>")

        urls.update(new_urls)

    original_mods = listings[: len(urls) - 1]
    dependencies = listings[len(urls) - 1 :]

    return original_mods, dependencies


def get_mod_listing(url: str) -> ModListing:
    """Creates a ModListing object from mod url."""
    logging.info(f"Getting info from: <{url}>")

    html = bs4.BeautifulSoup(get_data_from_url(url).text, features="html.parser")

    # Name.
    name = html.find("h1", class_="mt-0").text

    # Data from latest version.
    latest = html.find_all("table", class_="table mb-0")[1].find_all("tr")[1]
    date, version, _, download, *_ = latest.find_all("td")

    date = datetime.datetime.strptime(date.text, "%Y-%m-%d").date()
    version = version.text
    download = download.a["href"]

    # Dependency URLs.
    deps = [f.a["href"] for f in html.find_all("h5", class_="mt-0")]
    deps = [DOMAIN_SCHEMA + dep for dep in deps]

    logging.info(
        f"Got info for mod: {name}, version {version}, last updated {date.isoformat()}"
    )

    return ModListing(
        name=name,
        url=url,
        last_updated=date,
        version=version,
        download=download,
        dependencies=deps,
    )


def get_data_from_url(url: str) -> requests.models.Response:
    """Return data from a URL or None if it fails."""
    try:
        r = requests.get(url, timeout=5)
    # pylint: disable=broad-exception-caught]
    except Exception as e:
        exit_failure(f"Error obtaining URL <{url}>: {e}")

    if r.status_code != 200:
        exit_failure(f"URL <{url}> returned code {r.status_code}")

    return r


def exit_failure(mes, logging_function=logging.critical):
    """Exits the program with an error, logging the message."""
    logging_function(mes)
    sys.exit("Forcing program exit")


if __name__ == "__main__":
    try:
        __main()
    except SystemExit as __e:
        raise __e
    except Exception as __e:
        logging.critical(f"Unexpected exception: {__e}")
        raise __e
