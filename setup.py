from setuptools import setup, find_packages

with open("requirements.txt") as f:
    required = f.read().splitlines()

setup(
    name="diskforge",
    version="1.0",
    author="Omur Ozbahceliler",
    author_email="omur@rootifera.org",
    description="Multi-threaded disk formatter",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/rootifera/diskforge",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=required,
    entry_points={
        "console_scripts": [
            "diskforge=main:main",
        ],
    },
    include_package_data=True,
)
