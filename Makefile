.PHONY: quick integration ui perf full all gates-help

quick:
	./scripts/test_gates.sh quick

integration:
	./scripts/test_gates.sh integration

ui:
	./scripts/test_gates.sh ui

perf:
	./scripts/test_gates.sh perf

full:
	./scripts/test_gates.sh full

all:
	./scripts/test_gates.sh all

gates-help:
	@echo "Targets: quick integration ui perf full all"
