.PHONY: help install dev-install update uninstall which

help:
	@echo "Targets:"
	@echo "  install      - uv tool install ."
	@echo "  dev-install  - uv tool install --editable ."
	@echo "  update       - uv tool install --upgrade ."
	@echo "  uninstall    - uv tool uninstall ghg"
	@echo "  which        - prints uv tool dir and which ghg"

install:
	uv tool install .

dev-install:
	uv tool install --editable .

update:
	uv tool install --upgrade . || uv tool install .

uninstall:
	uv tool uninstall ghg

which:
	uv tool dir || true
	which ghg || true
