# Agent Team Architecture Documentation

## Overview

This project implements an autonomous development team using AI agents. Each agent has a specific role, persona, and mission, working together to manage and develop software projects.

## Design Principles

### 1. Modularity
- Each agent is self-contained in its own module
- Clear separation of concerns
- Easy to add new agents or modify existing ones

### 2. Extensibility
- Base agent class provides common functionality
- New agents extend `BaseAgent` and implement their own logic
- Plugin-like architecture for new capabilities

### 3. Security First
- Repository allowlist prevents unauthorized access
- Secrets managed via GitHub Secrets
- Never commit sensitive data
- Automated security scanning by Senior Developer Agent

### 4. Automation
- GitHub Actions for scheduled execution
- No manual intervention required
- Autonomous conflict resolution
- Automated CI/CD setup

## Agent Interaction Model

### Sequential Workflow

```
1. Product Manager runs → Creates ROADMAP.md
2. Interface Developer runs → Reads roadmap, creates UI tasks via Jules
3. Senior Developer runs → Reads roadmap, creates feature tasks via Jules
4. Jules executes tasks → Creates Pull Requests
5. PR Assistant runs → Reviews and merges PRs
```

### Communication

Agents don't communicate directly. They use:
- **ROADMAP.md**: Product Manager creates, others read
- **DESIGN.md**: Interface Developer creates, others reference
- **GitHub Issues**: All agents can create/reference
- **Pull Requests**: Created by Jules tasks, processed by PR Assistant

## Jules API Integration

### Task Creation Pattern

```python
jules_client.create_pull_request_task(
    repository="owner/repo",
    feature_description="...",
    agent_persona="Agent's persona injected here"
)
```

### Persona Injection

Each agent's persona is automatically injected into Jules tasks, ensuring Jules understands the context and requirements.

### Task Lifecycle

1. Agent analyzes repository
2. Agent creates Jules task with detailed instructions
3. Jules executes task asynchronously
4. Jules creates Pull Request
5. PR Assistant processes the PR

## Repository Allowlist

### Purpose
- Security: Prevent agents from accessing unauthorized repositories
- Control: Explicit opt-in for automation
- Audit: Track which repositories are managed

### Format

```json
{
  "repositories": [
    "owner/repo1",
    "owner/repo2"
  ]
}
```

### Management

```python
from src.config import RepositoryAllowlist

allowlist = RepositoryAllowlist()
allowlist.add_repository("owner/new-repo")
allowlist.is_allowed("owner/repo1")  # True
allowlist.remove_repository("owner/repo1")
```

## Configuration System

### Settings Hierarchy

1. Environment variables (highest priority)
2. Default values
3. Configuration files

### environment Variables

- `GITHUB_TOKEN`: Required for GitHub API access
- `JULES_API_KEY`: Required for Jules API access
- `GITHUB_OWNER`: Target GitHub user (default: juninmd)
- `GEMINI_API_KEY`: Optional, for AI-powered features
- Agent toggles: `PM_AGENT_ENABLED`, `UI_AGENT_ENABLED`, etc.

## Scheduling Strategy

### Staggered Execution

Agents run at different times to create a natural workflow:

- **9:00 AM**: Product Manager (planning)
- **11:00 AM**: Interface Developer (2 hours after PM)
- **1:00 PM**: Senior Developer (2 hours after UI)
- **Every 30 minutes**: PR Assistant (continuous monitoring, all repositories)

### Rationale

- Allows Jules tasks time to complete
- Prevents resource contention
- Creates logical dependency chain
- PR Assistant runs frequently to merge completed work across all repositories
- Development agents (PM, UI, Senior Dev) limited by allowlist
- PR Assistant has no repository restrictions for comprehensive PR management

## Error Handling

### Agent-Level

Each agent:
- Logs errors but continues processing other repositories
- Saves partial results
- Reports failures in execution summary

### System-Level

- GitHub Actions retries on transient failures
- Logs uploaded as artifacts for debugging
- Telegram notifications for critical failures (optional)

## Logging and Monitoring

### Structured Logging

```json
{
  "agent": "ProductManager",
  "timestamp": "2026-02-08T10:00:00Z",
  "processed": [...],
  "failed": [...]
}
```

### Artifacts

- Execution logs saved to `logs/` directory
- Uploaded to GitHub Actions artifacts
- Retained for 30 days

## Extensibility Guide

### Adding a New Agent

1. **Create Agent Class**
   ```python
   class MyAgent(BaseAgent):
       @property
       def persona(self) -> str:
           return "Your agent's persona"

       @property
       def mission(self) -> str:
           return "Your agent's mission"

       def run(self) -> Dict[str, Any]:
           # Implementation
           pass
   ```

2. **Add to Registry**
   - Update `src/agents/__init__.py`
   - Add runner function in `src/run_agent.py`

3. **Create Workflow**
   - Add `.github/workflows/my-agent.yml`
   - Configure schedule and secrets

4. **Document**
   - Update README with agent description
   - Add to architecture docs

### Adding New Features to Existing Agents

1. Extend agent class with new methods
2. Update `run()` method to include new logic
3. Add tests
4. Update documentation

## Testing Strategy

### Unit Tests
- Test individual agent methods
- Mock external dependencies (GitHub, Jules)
- Verify persona and mission properties

### Integration Tests
- Test agent interactions with real APIs (using test repositories)
- Verify workflow execution
- Test error handling

### End-to-End Tests
- Full workflow from PM to merge
- Verify Jules task creation and execution
- Validate PR Assistant behavior

## Security Considerations

### Secrets Management
- All API keys in GitHub Secrets
- Never log sensitive data
- Rotate keys regularly

### Repository Access
- Allowlist prevents unauthorized access
- Agents only have read/write to approved repos
- GitHub token scoped appropriately

### Code Injection Prevention
- Validate all inputs from GitHub API
- Sanitize data before passing to Jules
- No eval() or exec() of untrusted code

## Performance Optimization

### API Rate Limiting
- Respect GitHub API rate limits
- Use conditional requests where possible
- Implement exponential backoff

### Parallel Processing
- Process multiple repositories concurrently (future enhancement)
- Use async/await for I/O operations (future enhancement)

### Caching
- Cache repository metadata
- Reuse GitHub objects within execution
- Cache Jules task results

## Future Enhancements

### Planned Features
1. **AI Code Review Agent**: Deep code review using LLMs
2. **Documentation Agent**: Auto-generate and update docs
3. **Performance Agent**: Monitor and optimize application performance
4. **Security Auditor Agent**: Comprehensive security scans

### Infrastructure Improvements
1. Database for execution history
2. Web dashboard for monitoring
3. Slack/Discord integration
4. Custom Jules task templates

## Troubleshooting

### Common Issues

**Agent not running**
- Check GitHub Actions logs
- Verify secrets are configured
- Ensure repository is in allowlist

**Jules tasks failing**
- Verify Jules API key is valid
- Check Jules task logs
- Ensure repository has proper CI/CD

**PR Assistant not merging**
- Verify PR passes all checks
- Check PR author is in allowed list
- Ensure no merge conflicts

### Debug Mode

Set environment variable `DEBUG=true` for verbose logging:

```bash
DEBUG=true uv run run-agent product-manager
```

## Support and Contribution

### Getting Help
- Check documentation first
- Search existing issues
- Open new issue with detailed information

### Contributing
- Follow existing code style
- Add tests for new features
- Update documentation
- Submit PR with clear description

---

**Last Updated**: February 8, 2026
**Version**: 2.0.0
**Maintainer**: Junior (juninmd)
