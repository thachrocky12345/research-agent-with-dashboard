.PHONY: init dashboard dev clean

# Run the post-init hook to update docs and check dependencies
init:
	@bash .claude/hooks/post_init.sh
	@echo ""
	@echo "Now run /init inside Claude Code to sync AI context"

# Start the dashboard (requires EXP_DIR to be set)
dashboard:
	cd dashboard && npm run dev

# Alias for dashboard
dev: dashboard

# Clean generated files
clean:
	rm -rf dashboard/.next
	rm -rf dashboard/node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Install dashboard dependencies
install:
	cd dashboard && npm install

# Build dashboard for production
build:
	cd dashboard && npm run build

# Help
help:
	@echo "Available targets:"
	@echo "  init      - Update docs and check for dependency changes"
	@echo "  dashboard - Start the Next.js dashboard (set EXP_DIR first)"
	@echo "  dev       - Alias for dashboard"
	@echo "  install   - Install dashboard npm dependencies"
	@echo "  build     - Build dashboard for production"
	@echo "  clean     - Remove generated files"
