.PHONY: install seed serve test bench
install: ; pip install -e ".[dev]"
seed: ; brain seed
serve: ; brain serve
test: ; pytest -q
bench: ; brain bench
