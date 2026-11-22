# Task: Technical Debt Reduction for {{repository}}

## Identified Areas
{{details}}

## Instructions
You are a software architect focused on code quality and maintainability. Your goal is to identify and resolve technical debt in the specified areas.

### 1. Refactor Complex Logic
- Identify functions or classes with high cyclomatic complexity.
- Break down large methods into smaller, well-named helper functions.
- Simplify nested conditional blocks.

### 2. Elimination of Code Duplication
- Look for similar patterns across files and consolidate them into shared utilities or base classes.
- Follow the **DRY** (Don't Repeat Yourself), **KISS**, and **SOLID** principles.
- Apply **YAGNI** to avoid over-engineering.

### 3. Improve Standard Compliance
- Ensure code follows the project's style guide and best practices.
- Improve naming conventions to be more descriptive.
- Add necessary comments to explain *why* complex decisions were made (not just *how* the code works).

### 4. Remove Dead Code
- Identify and remove unused imports, variables, and unreachable code paths.

### 5. Testing & Verification (MANDATORY)
- **Do not break existing functionality.** All existing tests must pass.
- **You MUST write/update unit or integration tests** for all refactored code modules or functions.
- If code structure changes significantly, ensure tests still validate the same functionality. If new helper methods or logic are introduced, they must have dedicated tests covering edge cases.

## Deliverables
Create a PR with:
- Refactored code that is cleaner and easier to maintain.
- Corresponding unit/integration tests confirming the reliability and correct behavior of the refactored code.
- A summary of the technical debt resolved and tests run in the PR description.
- Verification that all tests pass.
