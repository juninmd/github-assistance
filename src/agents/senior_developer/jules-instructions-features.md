# Task: Feature Implementation for {{repository}}

## Features to Implement
{{features}}

## Implementation Guidelines

### 1. Planning Phase
- [ ] Review feature requirements thoroughly
- [ ] Check ROADMAP.md for priorities
- [ ] Identify dependencies and prerequisites
- [ ] Design API/component interfaces
- [ ] Plan database schema changes (if needed)

### 2. Architecture & Design
- [ ] Follow SOLID principles
- [ ] Use appropriate design patterns
- [ ] Consider scalability and performance
- [ ] Plan for error handling and edge cases
- [ ] Design with testability in mind

### 3. Development Standards

#### Code Quality
- Write clean, self-documenting code
- Use meaningful variable and function names
- Keep functions small and focused (single responsibility)
- Add comments for complex logic only
- Follow language-specific style guides

#### Security Considerations
- Validate all user inputs
- Sanitize outputs to prevent XSS
- Use parameterized queries (no SQL injection)
- Implement proper authentication/authorization
- Never hardcode secrets or credentials
- Follow OWASP security guidelines

#### Performance
- Optimize database queries (use indexes)
- Implement caching where appropriate
- Use async/await for I/O operations
- Lazy load resources when possible
- Profile and benchmark critical paths

### 4. Testing Requirements (MANDATORY)

#### Unit & Integration Tests
- **You MUST write corresponding unit and integration tests** for all newly added files, classes, methods, or functions.
- Test all business logic, covering edge cases, logical branches, and error scenarios.
- Aim for 100% test coverage on new changes (overall target 80%+ coverage).
- Do not complete the task or create a Pull Request without writing and verifying tests.
- Use descriptive test names and mock external dependencies.
- Test API endpoints end-to-end, database interactions, and verify error handling.

### 5. Documentation

#### Code Documentation
- Add JSDoc/docstrings for public APIs
- Document function parameters and return values
- Add examples for complex functions
- Update type definitions

#### Project Documentation
- Update README with new features
- Add usage examples
- Document configuration options
- Update API documentation
- Add troubleshooting guide if needed

### 6. CI/CD Integration
- Ensure all CI checks pass
- Add new tests to test suite
- Update build scripts if needed
- Verify deployment process works
- Test in staging environment

### 7. Code Review Preparation
- Self-review your changes
- Run linter and fix all issues
- Ensure consistent code formatting
- Remove debug code and console.logs
- Squash commits into logical units
- Write clear commit messages

### 8. Pull Request Guidelines

#### PR Description Template
```markdown
## 🎯 Objective
Brief description of what this PR does

## 🔄 Changes
- List of changes made
- Another change

## 🧪 Testing
- How to test these changes
- Test scenarios covered

## 📸 Screenshots/Videos
(if UI changes)

## ✅ Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No hardcoded secrets
- [ ] CI passes
- [ ] Self-reviewed
```

## Language-Specific Best Practices

### JavaScript/TypeScript
- Use TypeScript for type safety
- Prefer `const` over `let`, avoid `var`
- Use async/await over callbacks
- Implement proper error boundaries
- Use ESLint and Prettier

### Python
- Follow PEP 8
- Use type hints (Python 3.6+)
- Use virtual environments
- Implement proper exception handling
- Use Black for formatting

### Go
- Follow effective Go guidelines
- Use `go fmt` and `go vet`
- Handle errors explicitly
- Use interfaces for abstraction
- Implement context for cancellation

### Java
- Follow Java conventions
- Use dependency injection
- Implement proper exception hierarchy
- Use streams and lambdas (Java 8+)
- Apply builder pattern for complex objects

## Desktop Application Specifics

If building desktop apps (Electron, Tauri, etc.):
- [ ] Create installers for Windows/macOS/Linux
- [ ] Sign applications with proper certificates
- [ ] Implement auto-update mechanism
- [ ] Handle offline scenarios gracefully
- [ ] Optimize bundle size
- [ ] Add crash reporting
- [ ] Test on all target platforms

## Performance Optimization Checklist
- [ ] Profile application performance
- [ ] Optimize critical code paths
- [ ] Implement lazy loading
- [ ] Use connection pooling for databases
- [ ] Cache frequently accessed data
- [ ] Optimize asset loading (images, fonts)
- [ ] Minimize bundle size
- [ ] Use CDN for static assets

## Success Criteria
- Feature works as specified
- All tests pass (80%+ coverage)
- Documentation complete and accurate
- Code passes all linters and security checks
- Performance benchmarks met
- PR approved by maintainers

Create a comprehensive PR with all improvements and detailed documentation.
