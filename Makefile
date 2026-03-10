.PHONY: help token-report prompt-analysis clean

help:
	@printf "AI Tooling - Available targets:\n"
	@printf "  token-report    - Generate token usage report (opencode-token-report)\n"
	@printf "  token-serve     - Start local server with auto-regeneration\n"
	@printf "  prompt-analysis - Run prompt analysis pipeline\n"
	@printf "  clean           - Clean all output directories\n"
	@printf "\n"
	@printf "  ai-report       - Open token report in browser (run make token-report first)\n"

token-report:
	$(MAKE) -C tools/opencode-token-report report

token-serve:
	$(MAKE) -C tools/opencode-token-report serve

prompt-analysis:
	$(MAKE) -C tools/prompt-analysis all

clean:
	$(MAKE) -C tools/opencode-token-report clean
	$(MAKE) -C tools/prompt-analysis clean
