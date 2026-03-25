.PHONY: help engineering-report engineering-serve prompt-analysis clean

help:
	@printf "AI Tooling - Available targets:\n"
	@printf "  engineering-report  - Generate and open engineering report\n"
	@printf "  engineering-serve   - Start local server with auto-regeneration\n"
	@printf "  prompt-analysis     - Run prompt analysis pipeline\n"
	@printf "  clean               - Clean all output directories\n"

engineering-report:
	$(MAKE) -C tools/engineering-report open

engineering-serve:
	$(MAKE) -C tools/engineering-report serve

prompt-analysis:
	$(MAKE) -C tools/prompt-analysis all

clean:
	$(MAKE) -C tools/engineering-report clean
	$(MAKE) -C tools/prompt-analysis clean
