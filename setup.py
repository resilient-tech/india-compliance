from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

# get version from __version__ variable in india_compliance/__init__.py
from india_compliance import __version__ as version

setup(
    name="india_compliance",
    version=version,
    description="ERPNext app to simplify compliance with Indian Rules and Regulations",
    author="Resilient Tech",
    author_email="india.compliance@resilient.tech",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
