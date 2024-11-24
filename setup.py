from setuptools import setup, find_packages

setup(
    name="actronneoapi",
    version="0.1.0",
    author="Kurt Chrisford",
    author_email="kurt@chrisfords.com.au",
    description="Python API wrapper for the ActronNeoAPI.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/kclif9/actronneoapi",
    packages=find_packages(),
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
