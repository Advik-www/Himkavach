.PHONY: help setup test lint demo experiments report up clean

help:
	@echo "HimKavach Build Commands:"
	@echo "  make setup        - Install dependencies in editable mode"
	@echo "  make test         - Run full pytest test suite"
	@echo "  make lint         - Run ruff check and format check"
	@echo "  make demo         - Run Storm Night demonstration"
	@echo "  make experiments  - Run Monte Carlo experiment benchmarks"
	@echo "  make report       - Generate evaluation reports from stored runs"
	@echo "  make up           - Start Docker Compose services"
	@echo "  make clean        - Clean build artifacts and caches"

setup:
	python -m pip install -e ".[dev]"

test:
	python -m pytest tests/

lint:
	python -m ruff check .
	python -m ruff format --check .

demo:
	python -m himkavach_evaluation.demo --seed 42

experiments:
	python -m himkavach_evaluation.runner --config configs/experiments/mc_default.yaml

report:
	python -m himkavach_evaluation.report --input experiments/results/

up:
	docker-compose up -d

clean:
	python -c "import shutil, glob, os; [shutil.rmtree(p, ignore_errors=True) for p in glob.glob('**/__pycache__', recursive=True)]; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', 'build', 'dist', '*.egg-info']]"
