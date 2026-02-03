.PHONY: help all report report-md pairs chunks stats clean

OUTPUT_DIR := output

help:
	@printf "%s\n" "Targets:" \
		"  all    - Run report, pairs, chunks, stats" \
		"  report - Generate output/report.html (lab report)" \
		"  report-md - Generate output/report.md" \
		"  pairs  - Generate output/pairs.jsonl" \
		"  chunks - Generate output/chunks.jsonl" \
		"  stats  - Generate output/*.csv and *.svg" \
		"  clean  - Remove output/ directory"

all: pairs report chunks stats

report:
	@mkdir -p $(OUTPUT_DIR)
	python3 report_lab/main.py --in $(OUTPUT_DIR)/pairs.jsonl --out $(OUTPUT_DIR)/report.html --format html

report-md:
	@mkdir -p $(OUTPUT_DIR)
	python3 report_lab/main.py --in $(OUTPUT_DIR)/pairs.jsonl --out $(OUTPUT_DIR)/report.md --format md

pairs:
	@mkdir -p $(OUTPUT_DIR)
	python3 export_pairs/main.py --out $(OUTPUT_DIR)/pairs.jsonl

chunks:
	@mkdir -p $(OUTPUT_DIR)
	python3 chunk_pairs/main.py --in $(OUTPUT_DIR)/pairs.jsonl --out $(OUTPUT_DIR)/chunks.jsonl

stats:
	@mkdir -p $(OUTPUT_DIR)
	python3 stats/main.py --in $(OUTPUT_DIR)/pairs.jsonl --out-dir $(OUTPUT_DIR)

clean:
	rm -rf $(OUTPUT_DIR)
