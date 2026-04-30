.PHONY: quick integration ui perf full all gates-help

quick:
	bash ./scripts/test_gates.sh quick

integration:
	bash ./scripts/test_gates.sh integration

ui:
	bash ./scripts/test_gates.sh ui

perf:
	bash ./scripts/test_gates.sh perf

full:
	bash ./scripts/test_gates.sh full

all:
	bash ./scripts/test_gates.sh all

gates-help:
	@echo "Targets: quick integration ui perf full all"
