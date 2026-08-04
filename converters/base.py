class Converter:
    name = ""
    category = ""
    input_extensions = ()
    output_extension = ""

    def convert(self, input_file, output_file):
        raise NotImplementedError
