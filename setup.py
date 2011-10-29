
from setuptools import setup, find_packages

import babbler


setup(
    name="babbler",
    version=babbler.__version__,
    author="Stephen McDonald",
    author_email="stephen.mc@gmail.com",
    description=babbler.__doc__.replace("\n", " ").strip(),
    long_description=open("README.rst").read(),
    license="BSD",
    url="http://github.com/stephenmcd/babbler/",
    include_package_data=True,
    packages=find_packages(),
    install_requires=[r.strip() for r in open("requirements.txt") if r],
    entry_points="""
        [console_scripts]
        babbler=babbler.bot:main
    """,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Topic :: Communications",
        "Topic :: Text Processing",
    ]
)
