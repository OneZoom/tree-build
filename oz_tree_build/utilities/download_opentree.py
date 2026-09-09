"""Download Open Tree of Life synthesis data (tree + taxonomy) into a versioned folder.

Usage:
    download_opentree --version v16.1 --output-dir data/OpenTree

This fetches the synthesis manifest from the OpenTree GitHub repo, then downloads
the labelled supertree and OTT taxonomy for the requested synthesis version. Files
are placed in ``<output-dir>/<version>/`` with version-agnostic names:

    <output-dir>/<version>/labelled_supertree_simplified_ottnames.tre
    <output-dir>/<version>/draftversion.tre
    <output-dir>/<version>/taxonomy.tsv
"""

import argparse
import os
import os.path
import shutil
import tarfile
import tempfile

import requests

OT_SSL_VERIFY = not os.environ.get("OT_SSL_VERIFY_DISABLE")
SYNTHESIS_JSON_URL = (
    "https://raw.githubusercontent.com/OpenTreeOfLife/opentree" "/master/webapp/static/statistics/synthesis.json"
)


def fetch_synthesis_json():
    response = requests.get(SYNTHESIS_JSON_URL, verify=OT_SSL_VERIFY)
    response.raise_for_status()
    return response.json()


def find_synthesis_entry(synthesis_json, version):
    """Return the manifest entry whose ``version`` field matches *version*."""
    for entry in synthesis_json.values():
        if entry.get("version") == version:
            return entry
    available = [e["version"] for e in synthesis_json.values() if "version" in e]
    raise SystemExit(f"Version '{version}' not found in synthesis.json. " f"Available versions: {', '.join(available)}")


def download_file(version, output_dir, download_file="/labelled_supertree/labelled_supertree_ottnames.tre"):
    """Download the labelled supertree and produce the processed draftversion."""
    assert version.startswith("v")
    version_without_v = version[1:]
    url = f"https://files.opentreeoflife.org/synthesis/opentree{version_without_v}/output/{download_file}"
    out_path = os.path.join(output_dir, os.path.basename(url))

    print(f"Downloading {url} -> {out_path} ...")
    response = requests.get(url, verify=OT_SSL_VERIFY)
    response.raise_for_status()

    with open(out_path, "w") as f:
        f.write(response.text)


def download_taxonomy(ott_version_raw, output_dir):
    """Download and extract taxonomy.tsv from the OTT taxonomy tarball."""
    ott_version = ott_version_raw.split("draft")[0]
    taxonomy_url = f"https://files.opentreeoflife.org/ott/{ott_version}/{ott_version}.tgz"
    print(f"Downloading taxonomy from {taxonomy_url} ...")
    response = requests.get(taxonomy_url, verify=OT_SSL_VERIFY)
    response.raise_for_status()

    with tempfile.TemporaryDirectory() as tmpdir:
        tar_path = os.path.join(tmpdir, "taxonomy.tgz")
        with open(tar_path, "wb") as f:
            f.write(response.content)

        print("  Extracting taxonomy.tsv ...")
        with tarfile.open(tar_path, "r:gz") as tar:
            taxonomy_member = None
            for member in tar.getmembers():
                if member.name.endswith("/taxonomy.tsv"):
                    taxonomy_member = member
                    break
            if taxonomy_member is None:
                raise SystemExit("Could not find taxonomy.tsv in the taxonomy tarball")
            extracted = tar.extractfile(taxonomy_member)
            dest_path = os.path.join(output_dir, "taxonomy.tsv")
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(extracted, f)
            print(f"  Saved taxonomy to {dest_path}")


def main():
    parser = argparse.ArgumentParser(description="Download Open Tree of Life synthesis data into a versioned folder.")
    parser.add_argument(
        "--version",
        required=True,
        help='Synthesis version to download (e.g. "v16.1"). '
        "Must match the 'version' field in the OpenTree synthesis.json manifest.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/OpenTree",
        help="Parent directory for the versioned output folder (default: data/OpenTree).",
    )
    args = parser.parse_args()

    version = args.version
    if not version.startswith("v"):
        raise SystemExit(f"Version must start with 'v' (got '{version}')")

    print("Fetching synthesis manifest ...")
    synthesis_json = fetch_synthesis_json()
    entry = find_synthesis_entry(synthesis_json, version)
    print(f"Found synthesis {version} (OTT {entry['OTT_version']})")

    output_dir = os.path.join(args.output_dir, version)
    os.makedirs(output_dir, exist_ok=True)

    download_file(version, output_dir, "/labelled_supertree/labelled_supertree_ottnames.tre")
    download_file(version, output_dir, "/annotated_supertree/annotations.json")
    download_taxonomy(entry["OTT_version"], output_dir)
    print(f"Done. All files written to {output_dir}/")


if __name__ == "__main__":
    main()
