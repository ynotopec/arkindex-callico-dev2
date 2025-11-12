#!/usr/bin/env python
import os.path

from setuptools import find_packages, setup


def requirements(path):
    assert os.path.exists(path), "Missing requirements {}".format(path)
    with open(path) as f:
        return f.read().splitlines()


with open("callico/VERSION") as f:
    VERSION = f.read().strip()

install_requires = requirements("requirements.txt")

setup(
    name="callico",
    version=VERSION,
    description="Callico",
    author="Teklia",
    author_email="callico@teklia.com",
    python_requires=">=3.11",
    setup_requires=["setuptools>=78.0.0"],
    install_requires=install_requires,
    packages=find_packages(),
    include_package_data=True,
    py_modules=[
        "callico",
    ],
    scripts=[
        "callico/manage.py",
    ],
    license="AGPL-3.0-only",
    license_files=("LICENSE",),
)
