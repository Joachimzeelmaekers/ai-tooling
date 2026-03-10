.PHONY: help ai-report ai-serve prompt-analysis clean

help:
	@printf "AI Tooling - Available targets:\n"
	@printf "  ai-report       - Generate and open token usage report\n"
	@printf "  ai-serve        - Start local server with auto-regeneration\n"
	@printf "  prompt-analysis - Run prompt analysis pipeline\n"
	@printf "  clean           - Clean all output directories\n"

ai-report:
	$(MAKE) -C tools/token-report open

ai-serve:
	$(MAKE) -C tools/token-report serve

prompt-analysis:
	$(MAKE) -C tools/prompt-analysis all

clean:
	$(MAKE) -C tools/token-report clean
	$(MAKE) -C tools/prompt-analysis clean
