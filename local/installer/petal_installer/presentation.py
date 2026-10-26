"""Small display decisions shared by the GTK view and display-free checks."""
from pathlib import Path


def release_choices(records):
    choices = [record for record in records if record['installer_catalog']]
    if not records:
        message = 'No releases are published yet. When a PetalOS build is published, its version and build choices will appear here. You can also use an already downloaded build.'
    elif not choices:
        message = 'Published releases exist, but none has installer-ready build files yet. Choose an already downloaded installer build, or wait for a compatible release.'
    else:
        message = 'Choose a version, then a build. Builds may include a local AI agent.'
    return choices, message


def variant_title(variant):
    return variant['name'] + (' · local AI agent' if variant['local_ai'] else '')


def local_build_message(directory):
    root = Path(directory)
    if not (root / 'petalos-release.json').is_file() or not (root / 'selection.json').is_file():
        if (root / 'manifest.json').is_file():
            return 'This is an OS build output folder. It must first be exported for the installer with bundle-from-build. Earlier builds also need rebuilding for split storage.'
        return 'Choose the folder downloaded by Bloom. It contains petalos-release.json, selection.json and the build files. An ISO file alone cannot be used here.'
    return None
