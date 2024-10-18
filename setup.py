from setuptools import setup, Extension
import pathlib
import os

root_dir = pathlib.Path(__file__).parent

if os.environ.get("BUILD_EXTENSION") == "0":
    ext = []
else:
    ext = [
        Extension(
            'wsdatautil._wsframecoder',
            sources=['src/wsdatautil/_wsframecoder.c'],
            extra_compile_args=['-std=c99']
        )
    ]

setup(
    long_description=(root_dir / "README.rst").read_text("utf-8"),
    long_description_content_type="text/x-rst",
    ext_modules=ext
)
