# AGENTS.md

This file contains the core guidelines and constraints for AI agents working on the **github-assistance** repository.

## Core Principles

- **DRY (Don't Repeat Yourself)**: Avoid code duplication by consolidating logic into shared utilities or base classes.
- **KISS (Keep It Simple, Stupid)**: Favor simple, readable solutions over complex architectures.
- **SOLID**: Follow object-oriented design principles to ensure maintainability and scalability.
- **YAGNI (You Aren't Gonna Need It)**: Do not implement features or abstractions until they are actually needed.

## Development Standards

- **Productivity**: All development must be productive. Do not use mocks or fake implementations. Use mocks **ONLY** for tests.
- **File Length**: Each source file must have a **maximum of 180 lines of code**. Large files must be refactored into smaller, focused modules.
- **Test Coverage**: Maintain at least **80% test coverage** for all new logic.
- **Secrets**: NEVER hardcode or commit passwords, tokens, or keys. Use `.env` files and ensure `.gitignore` is up to date.

## Language and Formatting

- Always write instructions and guidelines for agents in **English**.
- Follow language-specific style guides (PEP 8 for Python).
