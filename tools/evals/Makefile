SHELL := /bin/bash
EVALS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
BIN := $(EVALS_DIR)bin/ai-eval

.PHONY: run list compare history report clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

run: ## Run evals (use HARNESS=path SUITE=name TAG=name MODEL=name AGENT=name)
	@$(BIN) run \
		$(if $(HARNESS),--harness $(HARNESS)) \
		$(if $(SUITE),--suite $(SUITE)) \
		$(if $(TAG),--tag $(TAG)) \
		$(if $(MODEL),--model $(MODEL)) \
		$(if $(AGENT),--agent $(AGENT))

dry-run: ## Dry run (show what would execute)
	@$(BIN) run --dry-run \
		$(if $(HARNESS),--harness $(HARNESS)) \
		$(if $(SUITE),--suite $(SUITE)) \
		$(if $(TAG),--tag $(TAG))

list: ## List available evals
	@$(BIN) list

compare: ## Compare two runs (use TAG1=x TAG2=y)
	@test -n "$(TAG1)" || (echo "Usage: make compare TAG1=x TAG2=y" && exit 1)
	@test -n "$(TAG2)" || (echo "Usage: make compare TAG1=x TAG2=y" && exit 1)
	@$(BIN) compare $(TAG1) $(TAG2)

history: ## Show run history (use LIMIT=n)
	@$(BIN) history $(if $(LIMIT),--limit $(LIMIT))

report: ## Show report for a run (use RUN=id)
	@test -n "$(RUN)" || (echo "Usage: make report RUN=id" && exit 1)
	@$(BIN) report $(RUN)

clean: ## Remove all results (careful!)
	@echo "Removing all results..."
	@find $(EVALS_DIR)results -mindepth 1 -not -name '.gitkeep' -exec rm -rf {} + 2>/dev/null || true
	@echo "Done."
