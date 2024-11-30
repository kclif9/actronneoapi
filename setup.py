from setuptools import setup, find_packages

setup(
    name="actron-neo-api",
    version="0.0.10",
    author="Kurt Chrisford",
    author_email="soft.year7030@fastmail.com",
    description="Python API wrapper for the Actron Neo API.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/kclif9/actronneoapi",
    packages=find_packages(where="src"),  # Look for packages inside src/
    package_dir={"": "src"},  # Root is src/
    install_requires=[
        "aiohttp>=3.8.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)