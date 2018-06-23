import os
from setuptools import find_packages, setup

os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="asyncio-http-parser",
    version="0.0.1",
    packages=find_packages(),
    # install_requires=[],
    license="MIT License",
    author="Jordan E.",
    author_email="jermff@gmail.com",
    entry_points={"console_scripts": ["fikki = asyncio_http_parser.server:main"]},
)
