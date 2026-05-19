#!/usr/bin/env python3
"""Direct technical debt reduction for vibe-kanban."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.agents.opencode_runner import OpencodeRunner
from src.config.repository_allowlist import RepositoryAllowlist
from src.github_client import GithubClient
from src.notifications.telegram import TelegramNotifier


TECH_DEBT_TEMPLATE = """You are a senior software engineer performing technical debt reduction on a TypeScript project.

## Critical Requirement
YOU MUST MAKE ACTUAL CODE CHANGES. Do not just analyze - actually refactor the code.

## Repository: juninmd/vibe-kanban
The codebase has these specific problems:

1. **src/app.ts** (77KB, 2500+ lines) - massive file that needs splitting
2. **src/server.ts** (83KB, 2500+ lines) - massive server file needing modularization  
3. **src/utils/** - many utility files that should be organized into subdirectories

## Your Task - REFACTOR THE CODE

### Step 1: Read src/app.ts
- Understand its structure and exports
- Identify logical sections (routes, handlers, utilities, types)
- Create new files: src/app/routes.ts, src/app/handlers.ts, src/app/types.ts, src/app/utils.ts
- Move relevant code to new files, keep minimal exports in app.ts

### Step 2: Read src/server.ts  
- Identify route handlers, middleware, business logic
- Create: src/server/routes.ts, src/server/middleware.ts, src/server/services.ts
- Refactor server.ts to import from these modules

### Step 3: Organize utils
- Create src/utils/http/ for HTTP-related utilities
- Create src/utils/validation/ for validation functions
- Move files to appropriate subdirectories

### Step 4: Verify
- Run existing tests: pnpm test
- Fix any issues found

## Important Rules
- Keep the same API/interface - don't break calling code
- Preserve all functionality
- Use consistent TypeScript types
- Follow existing code style

## Output
After refactoring, provide:
1. List of files created/modified
2. Summary of what was refactored
3. Test results showing everything still works
"""

REPO = "juninmd/vibe-kanban"
TITLE = "Technical Debt Reduction"

def main():
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)

    allowlist = RepositoryAllowlist("config/repositories.json")
    if not allowlist.is_allowed(REPO):
        print(f"ERROR: {REPO} not in allowlist")
        sys.exit(1)

    github_client = GithubClient(github_token)
    telegram = TelegramNotifier()
    opencode = OpencodeRunner(allowlist, print, github_client, telegram)

    # Override the model selection to use a more capable model
    original_get_model = opencode.get_random_free_opencode_model
    
    # Force use of deepseek model which tends to be more capable
    import random
    original_cache = OpencodeRunner._model_cache
    OpencodeRunner._model_cache = "opencode/deepseek-v4-flash-free"
    
    instructions = TECH_DEBT_TEMPLATE.format(repository=REPO)
    result = opencode.run_on_repo(REPO, instructions, TITLE, agent_name="senior_developer")
    
    # Restore
    OpencodeRunner._model_cache = original_cache

    print(f"Result: {result}")
    if result.get("status") == "success":
        print(f"PR URL: {result.get('pr_url')}")
    else:
        print(f"Error: {result.get('error', result.get('status'))}")
        sys.exit(1)

if __name__ == "__main__":
    main()