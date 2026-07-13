from PIL import Image
from converters.base import Converter
import os

class ImageConverter(Converter):
    """Generic image converter using Pillow."""
    category = "Image"

    def __init__(self, name, input_extensions, output_extension):
        self.name = name
        self.input_extensions = tuple(input_extensions)
        self.output_extension = output_extension

    def convert(self, input_file, output_file):
        img = Image.open(input_file)
        # Convert to RGB if necessary (e.g., for JPEG)
        if self.output_extension.lower() in ('.jpg', '.jpeg') and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        # For other formats, Pillow handles it automatically
        img.save(output_file, format=self._get_format())

    def _get_format(self):
        ext = self.output_extension.lower()
        format_map = {
            '.jpg': 'JPEG',
            '.jpeg': 'JPEG',
            '.png': 'PNG',
            '.gif': 'GIF',
            '.bmp': 'BMP',
            '.tiff': 'TIFF',
            '.webp': 'WEBP',
            '.heif': 'HEIF',
            '.heic': 'HEIC',
            '.eps': 'EPS',
        }
        return format_map.get(ext, ext.lstrip('.').upper())


# Generate all image converters
image_presets = [
    # From PNG
    ("PNG → JPG", (".png",), ".jpg"),
    ("PNG → JPEG", (".png",), ".jpeg"),
    ("PNG → GIF", (".png",), ".gif"),
    ("PNG → WebP", (".png",), ".webp"),
    ("PNG → HEIF", (".png",), ".heif"),
    ("PNG → HEIC", (".png",), ".heic"),
    ("PNG → TIFF", (".png",), ".tiff"),
    ("PNG → BMP", (".png",), ".bmp"),
    ("PNG → EPS", (".png",), ".eps"),
    # From JPG/JPEG
    ("JPG → PNG", (".jpg", ".jpeg"), ".png"),
    ("JPG → GIF", (".jpg", ".jpeg"), ".gif"),
    ("JPG → WebP", (".jpg", ".jpeg"), ".webp"),
    ("JPG → HEIF", (".jpg", ".jpeg"), ".heif"),
    ("JPG → HEIC", (".jpg", ".jpeg"), ".heic"),
    ("JPG → TIFF", (".jpg", ".jpeg"), ".tiff"),
    ("JPG → BMP", (".jpg", ".jpeg"), ".bmp"),
    ("JPG → EPS", (".jpg", ".jpeg"), ".eps"),
    # From GIF
    ("GIF → PNG", (".gif",), ".png"),
    ("GIF → JPG", (".gif",), ".jpg"),
    ("GIF → WebP", (".gif",), ".webp"),
    ("GIF → TIFF", (".gif",), ".tiff"),
    # From WebP
    ("WebP → PNG", (".webp",), ".png"),
    ("WebP → JPG", (".webp",), ".jpg"),
    ("WebP → GIF", (".webp",), ".gif"),
    # From TIFF
    ("TIFF → PNG", (".tiff",), ".png"),
    ("TIFF → JPG", (".tiff",), ".jpg"),
    # From BMP
    ("BMP → PNG", (".bmp",), ".png"),
    ("BMP → JPG", (".bmp",), ".jpg"),
    # From HEIF/HEIC (requires pillow-heif)
    ("HEIF → PNG", (".heif", ".heic"), ".png"),
    ("HEIF → JPG", (".heif", ".heic"), ".jpg"),
]

# Build the list
ALL_IMAGE_CONVERTERS = []
for name, ins, out in image_presets:
    ALL_IMAGE_CONVERTERS.append(ImageConverter(name, ins, out))