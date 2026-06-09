from setuptools import setup, Extension
from Cython.Build import cythonize

setup(
    ext_modules = cythonize([
        Extension("oping", ["oping.pyx"], libraries=["oping"])
    ], language_level=3)
)
