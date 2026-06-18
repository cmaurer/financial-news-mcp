
install:
	@pipx install . --force

register:
	@claude mcp remove --scope user financial-news 2>/dev/null || true
	@claude mcp add --scope user financial-news financial-news-mcp
