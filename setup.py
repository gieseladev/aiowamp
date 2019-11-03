import setuptools
import aiowamp

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="aiowamp",
    version=aiowamp.__version__,
    author=aiowamp.__author__,
    author_email="team@giesela.dev",
    url="https://github.com/gieseladev/wampio",

    licence="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",

    install_requires=[
        "aiobservable",
        "msgpack",
        "websockets",
    ],

    packages=setuptools.find_packages(exclude=("docs", "tests")),
    package_data={
        "aiowamp": ["py.typed"],
    },
)
