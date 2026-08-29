.PHONY: install test lint check demo dashboard experiment

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .

check: lint test

demo:
	python -m lyceum run --once --demo

dashboard:
	python -m lyceum dashboard

experiment:
	python -m lyceum experiment

