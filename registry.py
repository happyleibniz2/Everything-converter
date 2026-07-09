from pathlib import Path

from converters.image_converter import PNGtoJPG
from converters.video_converter import ALL_FFMPEG_CONVERTERS

CONVERTERS = [PNGtoJPG()] + ALL_FFMPEG_CONVERTERS


def normalize_extension(extension):
    extension = str(extension).strip().lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return extension


def find_converters_for_extension(extension):
    normalized_extension = normalize_extension(extension)
    return [
        converter
        for converter in CONVERTERS
        if normalized_extension in converter.input_extensions
    ]


def find_converters(input_file):
    input_file = str(input_file)
    extension = Path(input_file).suffix or input_file
    return find_converters_for_extension(extension)


def find_converter(input_file):
    converters = find_converters(input_file)
    return converters[0] if converters else None


def search_converters(query, converters=None):
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
