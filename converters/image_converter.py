from PIL import Image

from converters.base import Converter


class PNGtoJPG(Converter):

    name = "PNG → JPG"
    category = "Image"

    def convert(self, input_file, output_file):

        img = Image.open(input_file)

        if img.mode == "RGBA":
            img = img.convert("RGB")

        img.save(output_file, "JPEG")