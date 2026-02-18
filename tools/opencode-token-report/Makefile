.PHONY: help report clean

OUTPUT_DIR := output

help:
	@printf "%s\n" "Targets:" \
		"  report - Generate output/latest.html from local opencode session data" \
		"  clean  - Remove output/ directory"

report:
	@mkdir -p $(OUTPUT_DIR)
	python3 main.py

clean:
	rm -rf $(OUTPUT_DIR)
