"""
Collects Lethal Company mods from Thunderstore (thunderstore.io).
"""

import argparse
import bs4
import dataclasses
import datetime
import logging
import pathlib
import re
import requests
import sys
import urllib.parse

DOMAIN = "thunderstore.io"
DOMAIN_SCHEMA = f"https://{DOMAIN}"

# pylint: disable=logging-fstring-interpolation


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


def __main():
    """Collects settings from command line arguments."""
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
        "-c",
        "--check-version",
        action="store_true",
        help="Check if mods have been updated for the latest version",
    )
    parser.add_argument(
        "-e",
        "--export",
        nargs="?",
        default=sys.stdout,
        type=pathlib.Path,
        help="Export formatted mod list from acquired data",
    )

    args = parser.parse_args()

    # TODO: implement version checking.
    assert not args.check_version, "Version checking not implemented"

    # Extract all URLs from file.
    urls = get_urls_from_file(args.mod_list_file)

    # Check if all URLs are from the correct domain.
    for url in urls:
        if urllib.parse.urlparse(url).netloc != DOMAIN:
            raise ValueError(f"URL not from {DOMAIN}: {url}")

    # Collect mod data.
    original_mods, dependencies = collect_mod_data(urls)

    # Export formatted mod list, if requested.
    if args.export:
        export_mod_list(args.export, original_mods)

    # Download all mods.
    all_mods = original_mods[::]
    all_mods.extend(dependencies)
    for mod in all_mods:
        download_mod_from_listing(mod)


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
        for listing in listings:
            name = listing.name
            url = listing.url
            line = f"{name}\n<{url}>\n\n"
            f.write(line)


def download_mod_from_listing(mod: ModListing):
    """Download mod from ModListing using given URL and data."""
    logging.info(f"Downloading mod: {mod.name}")

    path = f"{mod.full_id()}.zip"
    file = get_data_from_url(mod.download)

    logging.info(f"Saving mod {mod.name} as {path}")

    with open(path, mode="wb") as f:
        for chunk in file.iter_content(chunk_size=1024):
            f.write(chunk)


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
            break

        logging.info(f"New dependencies found: <{'>, <'.join(new_urls)}>")

        urls.update(new_urls)

    original_mods = listings[: len(urls)]
    dependencies = listings[len(urls) :]

    return original_mods, dependencies


def get_mod_listing(url: str) -> ModListing:
    """Creates a ModListing object from mod url."""
    logging.info(f"Getting info from: <{url}>")

    html = get_data_from_url(url).text

    if html is None:
        logging.critical("Failed to obtain mod info")
        exit_failure()

    html = bs4.BeautifulSoup(html, features="html.parser")

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


def get_data_from_url(url: str) -> str | None:
    """Return data from a URL or None if it fails."""
    try:
        r = requests.get(url, timeout=5)
    # pylint: disable=broad-exception-caught]
    except Exception as e:
        logging.critical(f"Error obtaining URL <{url}>: {e}")
        return

    if r.status_code != 200:
        logging.critical(f"URL <{url}> returned code {r.status_code}")
        return

    return r


def exit_failure():
    """Exits the program with an error."""
    sys.exit("Forcing program exit")


if __name__ == "__main__":
    try:
        logging.getLogger().setLevel(logging.INFO)
        __main()
    except SystemExit as __e:
        raise __e
    except Exception as __e:
        logging.critical(f"Unexpected exception: {__e}")
        raise __e
