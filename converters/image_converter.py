from PIL import Image

from converters.base import Converter


class PNGtoJPG(Converter):

    name = "PNG → JPG"
    category = "Image"
    input_extensions = (".png",)
    output_extension = ".jpg"

    def convert(self, input_file, output_file):

        img = Image.open(input_file)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(output_file, "JPEG")
