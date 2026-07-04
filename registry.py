from pathlib import Path

from converters.image_converter import PNGtoJPG

CONVERTERS = [
    PNGtoJPG(),
]


def find_converter(input_file):
    """Return the first converter that supports the input file extension."""

    extension = Path(input_file).suffix.lower()

    for converter in CONVERTERS:
        if extension in converter.input_extensions:
            return converter

    return None


"""
EXAMPLES:
CONVERTERS = [
    PNGtoJPG(),
    JPGtoPNG(),
    PNGtoWEBP(),
    WEBPtoPNG(),
    PDFtoImage(),
    MP4toGIF(),
    ...
]
"""
