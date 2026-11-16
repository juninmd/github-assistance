# Task: Codebase Modernization for {{repository}}

## Identified Areas
{{details}}

## Instructions
You are a modernization specialist. Your goal is to bring this codebase up to current industry standards and best practices.

### 1. JavaScript to TypeScript Migration
- Convert identified `.js` files to `.ts`.
- Define proper interfaces and types for all data structures and function signatures.
- Minimize the use of `any`.

### 2. CommonJS to ES Modules (ESM)
- Replace `require()` and `module.exports` with `import` and `export`.
- Update configuration files if necessary (e.g., `package.json` with `"type": "module"`).

### 3. Async/Await Refactoring
- Identify legacy callback patterns or `.then()` chains.
- Refactor them to use `async` and `await` for improved readability and error handling.

### 4. Modern Language Features
- Use modern syntax (e.g., optional chaining, nullish coalescing, destructuring) where it improves the code.

### 5. Test Verification & Generation (MANDATORY)
- **You MUST write or update corresponding unit/integration tests** to verify all modernized functions, classes, or modules.
- If code is converted from JS to TS, ensure that tests run successfully and type safety is verified.
- If code paths are refactored (e.g., from promise chains to async/await), add tests to verify edge cases and error paths. Do not submit a PR without valid tests.

## Deliverables
Create a PR with:
- Modernized code files.
- Corresponding unit/integration tests covering all refactored/migrated code.
- Updated build/test configuration if migration requires it.
- A detailed list of changes and migration steps in the PR description.
