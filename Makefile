.PHONY: setup-githooks lint-markdown lint-all-markdown

setup-githooks:
	git config core.hooksPath .githooks
	@echo "Git hooks configured to use .githooks/"

lint-markdown:
	scripts/lint-markdown.sh --pre-commit

lint-all-markdown:
	scripts/lint-markdown.sh
