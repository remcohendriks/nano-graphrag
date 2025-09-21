import setuptools
from setuptools import find_packages

with open("readme.md", "r") as fh:
    long_description = fh.read()


vars2find = ["__author__", "__version__", "__url__"]
vars2readme = {}
with open("./nano_graphrag/__init__.py") as f:
    for line in f.readlines():
        for v in vars2find:
            if line.startswith(v):
                line = line.replace(" ", "").replace('"', "").replace("'", "").strip()
                vars2readme[v] = line.split("=")[1]

# Core dependencies (without transformers/torch)
core_deps = [
    "future>=1.0.0",
    "openai",
    "tiktoken",
    "networkx",
    "graspologic",
    "nano-vectordb",
    "hnswlib",
    "xxhash",
    "tenacity",
    "dspy-ai",
    "neo4j",
    "aioboto3",
    "redis[hiredis]>=5.0.0",
]

setuptools.setup(
    name="nano-graphrag",
    url=vars2readme["__url__"],
    version=vars2readme["__version__"],
    author=vars2readme["__author__"],
    description="A simple, easy-to-hack GraphRAG implementation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=core_deps,
    extras_require={
        "qdrant": ["qdrant-client>=1.7.0"],
        "hybrid": [
            "transformers>=4.36.0",
            "torch>=2.0.0",
        ],
        "all": [
            "qdrant-client>=1.7.0",
            "transformers>=4.36.0",
            "torch>=2.0.0",
        ],
    },
)
