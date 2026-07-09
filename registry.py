from pathlib import Path

from converters.image_converter import PNGtoJPG
from converters.video_converter import ALL_FFMPEG_CONVERTERS

CONVERTERS = [PNGtoJPG()] + ALL_FFMPEG_CONVERTERS


def normalize_extension(extension):
    """Return a lowercase extension that always starts with a dot."""
    extension = str(extension).strip().lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return extension


def find_converters_for_extension(extension):
    """Return all converters that support an input extension."""
    normalized_extension = normalize_extension(extension)
    return [
        converter
        for converter in CONVERTERS
        if normalized_extension in converter.input_extensions
    ]


def find_converters(input_file):
    """Return all converters that support an input file path or extension."""
    input_file = str(input_file)
    extension = Path(input_file).suffix or input_file
    return find_converters_for_extension(extension)


def find_converter(input_file):
    """Return the first converter that supports the input file extension."""
    converters = find_converters(input_file)
    if converters:
        return converters[0]
    return None


def search_converters(query, converters=None):
    """Return converters matching a search query across names and extensions."""
    query = query.strip().lower()
    if converters is None:
        converters = CONVERTERS

    if not query:
        return list(converters)

    matches = []
    for converter in converters:
        searchable = " ".join([
            converter.name,
            converter.category,
            *converter.input_extensions,
            converter.output_extension,
        ]).lower()
        if query in searchable:
            matches.append(converter)

    return matches