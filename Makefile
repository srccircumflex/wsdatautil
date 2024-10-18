.PHONY: default build types tests clean

export PYTHONASYNCIODEBUG=1
export PYTHONPATH=src
export PYTHONWARNINGS=default

build:
	python setup.py build_ext --inplace

types:
	mypy --strict src

tests:
	python -m unittest

clean:
	find src -name '*.so' -delete
	find . -name '*.pyc' -delete
	find . -name __pycache__ -delete
	rm -rf .mypy_cache build dist MANIFEST src/wsdatautil.egg-info
