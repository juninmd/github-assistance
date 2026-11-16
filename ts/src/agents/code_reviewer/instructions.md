# Code Reviewer Agent 👀

## Overview
The Code Reviewer Agent performs automated code reviews on pull requests using AI analysis. It provides constructive feedback on code quality, best practices, potential bugs, and security issues.

## Responsibilities

### Primary Functions
1. **Code Quality Review**: Assess code maintainability, readability, and structure
2. **Best Practices Check**: Ensure adherence to coding standards and design patterns
3. **Bug Detection**: Identify potential bugs, logic errors, and edge cases
4. **Security Analysis**: Detect security vulnerabilities and unsafe practices
5. **Performance Review**: Identify performance bottlenecks and optimization opportunities

### Review Criteria
- **Code Structure**: Proper separation of concerns, modularity
- **Naming Conventions**: Clear, descriptive variable and function names
- **Error Handling**: Proper exception handling and error messages
- **Testing**: Adequate test coverage and test quality
- **Documentation**: Code comments and docstrings where needed
- **Security**: No hardcoded secrets, SQL injection risks, XSS vulnerabilities
- **Performance**: Efficient algorithms, no unnecessary loops or redundant operations

## Configuration

### Environment Variables
```bash
ENABLE_AI=true                    # Required for AI-powered reviews
AI_PROVIDER=gemini               # AI provider (gemini, ollama, openai)
AI_MODEL=gemini-2.5-flash        # AI model to use
CODE_REVIEWER_ENABLED=true       # Enable this agent
```

### Review Settings
- **Review Frequency**: On new PR creation and updates
- **Review Scope**: All files changed in the PR
- **Comment Style**: Constructive, educational, actionable
- **Severity Levels**: Critical, High, Medium, Low, Info

## Workflow

1. **PR Detection**: Find open PRs in allowed repositories
2. **Change Analysis**: Get PR diff and analyze code changes
3. **AI Review**: Send code to AI for analysis
4. **Issue Classification**: Categorize findings by severity
5. **Comment Posting**: Post review comments on the PR
6. **Summary Report**: Send Telegram notification with summary

## Example Review Comments

### Critical Issue
```markdown
🔴 **Critical: Potential SQL Injection**
Line 45: User input is directly concatenated into SQL query.

**Risk**: An attacker could manipulate the query to access unauthorized data.

**Suggestion**: Use parameterized queries or an ORM.
```python
# Instead of:
query = f"SELECT * FROM users WHERE id = {user_id}"

# Use:
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))
```

### Code Quality Issue
```markdown
💡 **Suggestion: Extract Complex Logic**
Lines 120-145: This function has multiple responsibilities.

**Impact**: Harder to test and maintain.

**Suggestion**: Extract separate functions for validation, processing, and response.
```

## Metrics Tracked
- **Reviews Performed**: Number of PRs reviewed
- **Issues Detected**: Total issues found by severity
- **Suggestions Acceptance Rate**: Percentage of suggestions applied
- **Review Time**: Average time to review a PR
- **False Positives**: Issues marked as invalid by developers

## Integration with Other Agents
- **Senior Developer Agent**: May create tasks based on repeated issues
- **PR Assistant Agent**: Works together to improve PR quality
- **Security Scanner Agent**: Complements with runtime secret scanning

## Future Enhancements
- [ ] Learn from developer feedback on suggestions
- [ ] Custom rule configuration per repository
- [ ] Integration with static analysis tools (pylint, eslint)
- [ ] Automated fix suggestions (not just comments)
- [ ] Duplicate code detection across repositories
