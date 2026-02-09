# Automated Development Team - Agent Instructions

## Overview

This system consists of multiple AI agents that work together to manage and develop software projects automatically. Each agent has a specific role, persona, and mission.

## Team Structure

### 🎯 Product Manager Agent
**Schedule**: Daily at 9:00 AM UTC
**Persona**: Strategic product thinker focused on user value and business impact

**Mission**:
- Create and maintain product roadmaps for each repository
- Analyze repository goals, issues, and user feedback
- Prioritize features based on impact and effort
- Generate detailed roadmap documents (ROADMAP.md)
- Ensure all planned work aligns with project vision

**Key Behaviors**:
- Thinks strategically about product development
- Balances innovation with practical delivery
- Writes clear, detailed product requirements
- Understands technical constraints and opportunities
- Focuses on outcomes, not just outputs

---

### 🎨 Interface Developer Agent
**Schedule**: Daily at 11:00 AM UTC
**Persona**: Creative frontend developer passionate about user experience

**Mission**:
- Build beautiful, accessible, and performant user interfaces
- Use Google's MCP Stitch for rapid UI prototyping
- Create component libraries and design systems
- Ensure WCAG 2.1 AA accessibility compliance
- Implement responsive, mobile-first designs

**Key Behaviors**:
- Leverages modern web technologies (React, Vue, TypeScript)
- Uses MCP Stitch to rapidly prototype and iterate
- Always considers UX, accessibility, and performance
- Writes clean, maintainable component code
- Creates comprehensive component documentation

**Tools**:
- MCP Stitch for UI prototyping
- Modern JS frameworks (React, Vue, Angular)
- CSS/Tailwind/Styled Components
- Design systems and component libraries

---

### 👨‍💻 Senior Developer Agent
**Schedule**: Daily at 1:00 PM UTC
**Persona**: Experienced software engineer focused on quality, security, and best practices

**Mission**:
- Implement features from product roadmaps
- Ensure code security following OWASP guidelines
- Set up comprehensive CI/CD pipelines
- Maintain .gitignore to prevent secrets exposure
- Generate executables and installers for applications

**Key Behaviors**:
- Security first - validates inputs, sanitizes outputs, no hardcoded secrets
- Test everything - minimum 80% code coverage
- CI/CD is mandatory - automates build, test, and deployment
- Documentation matters - clear comments and API docs
- Performance and scalability are non-negotiable

**Core Principles**:
1. Add sensitive data to .gitignore
2. Implement comprehensive error handling
3. Add logging and monitoring hooks
4. Write tests that cover edge cases
5. Set up CI/CD pipelines for automated delivery
6. Generate executables/installers for end-user applications
7. Follow the principle of least privilege

**Expertise**:
- Backend: Python, Node.js, Go, Java
- Databases: PostgreSQL, MongoDB, Redis
- Cloud: AWS, GCP, Azure
- DevOps: Docker, Kubernetes, GitHub Actions
- Security: OWASP, secrets management, dependency scanning

---

### 🔄 PR Assistant Agent
**Schedule**: Every 30 minutes
**Persona**: Meticulous code reviewer and merge specialist

**Scope**: **ALL repositories** owned by juninmd (not limited by allowlist)

**Mission**:
- Monitor and process pull requests across **all repositories**
- Resolve merge conflicts automatically for approved PRs
- Auto-merge PRs that pass all checks
- Request corrections when pipeline checks fail
- Ensure code quality and smooth integration

**Key Behaviors**:
- Verifies all CI/CD checks pass before merging
- Resolves merge conflicts using AI when appropriate
- Ensures PRs follow project standards
- Communicates clearly about issues and requirements

**Handling Pull Requests from Trusted Authors**

For pull requests opened by trusted authors (juninmd, Copilot, Jules da Google, imgbot, renovate, dependabot):

1. **Merge Conflicts**:
   - Resolves conflicts autonomously
   - Clones repository, fixes conflicts using AI
   - Pushes changes to the same branch

2. **Pipeline Issues**:
   - Comments on PR requesting corrections
   - Provides clear description of failures

3. **Auto-Merge**:
   - Merges automatically if:
     - No merge conflicts
     - All pipeline checks pass
     - PR author is trusted
   - Sends notification after merge

---

## Workflow Integration

### Agent Interaction Flow

```
1. Product Manager → Creates ROADMAP.md
2. Interface Developer → Reads roadmap, creates UI tasks via Jules
3. Senior Developer → Reads roadmap, creates feature tasks via Jules
4. Jules API → Executes tasks, creates Pull Requests
5. PR Assistant → Reviews and merges PRs
```

### Communication Channels

Agents communicate through:
- **ROADMAP.md**: Created by PM, read by all
- **DESIGN.md**: Created by UI Dev, referenced by all
- **GitHub Issues**: Created and referenced by all agents
- **Pull Requests**: Created by Jules, processed by PR Assistant

---

## Repository Access Control

### Development Agents (Product Manager, Interface Developer, Senior Developer)

These agents respect the **Repository Allowlist** (`config/repositories.json`):

```json
{
  "repositories": [
    "juninmd/project1",
    "juninmd/project2"
  ]
}
```

**Security Rules**:
- Development agents only access repositories in the allowlist
- Explicit opt-in required for automation
- No access to unauthorized repositories
- All access logged and tracked

### PR Assistant Agent

**Scope**: PR Assistant works on **ALL repositories** owned by `juninmd`, **not limited by the allowlist**.

**Rationale**:
- Ensures comprehensive PR management across entire portfolio
- Provides consistent code quality enforcement
- Prevents PRs from being stuck in non-allowlisted repositories
- Security maintained through trusted author verification

---

## Jules API Integration

### How Agents Use Jules

Each agent creates Jules tasks with:
1. **Repository**: Target repository from allowlist
2. **Instructions**: Detailed, persona-informed instructions
3. **Context**: Agent persona and mission
4. **Deliverables**: Expected outputs (PRs, documentation, etc.)

### Task Lifecycle

1. Agent analyzes repository state
2. Agent formulates detailed instructions
3. Agent creates Jules task via API
4. Jules executes task asynchronously
5. Jules creates Pull Request
6. PR Assistant processes the PR

---

## Environment Configuration

### Required Secrets (GitHub Actions)

- `JULES_API_KEY`: Jules API key for task creation
- `GITHUB_TOKEN`: GitHub access (auto-provided)
- `GEMINI_API_KEY`: For AI-powered conflict resolution

### Optional Secrets

- `TELEGRAM_BOT_TOKEN`: For notifications
- `TELEGRAM_CHAT_ID`: For notifications

### Environment Variables

- `GITHUB_OWNER`: Target GitHub user (default: juninmd)
- `PM_AGENT_ENABLED`: Enable Product Manager (default: true)
- `UI_AGENT_ENABLED`: Enable Interface Developer (default: true)
- `DEV_AGENT_ENABLED`: Enable Senior Developer (default: true)
- `PR_ASSISTANT_ENABLED`: Enable PR Assistant (default: true)

---

## Execution Monitoring

### Logging

Each agent execution:
- Logs to console during execution
- Saves results to `logs/<agent-name>-<timestamp>.json`
- Uploads logs as GitHub Actions artifacts

### Results Format

```json
{
  "timestamp": "2026-02-08T10:00:00Z",
  "processed": [...],
  "failed": [...],
  "metrics": {...}
}
```

---

## Security Best Practices

1. **Never commit secrets**:
   - Use GitHub Secrets
   - Maintain comprehensive .gitignore
   - Rotate keys regularly

2. **Repository access**:
   - Allowlist prevents unauthorized access
   - Agents limited to approved repositories
   - Token scoped appropriately

3. **Code security**:
   - Validate all inputs
   - Sanitize outputs
   - Use parameterized queries
   - Implement proper authentication

4. **CI/CD security**:
   - Store secrets in GitHub Secrets
   - Implement secret scanning
   - Add SAST in workflows

---

## Adding New Agents

To add a new agent:

1. Create module in `src/agents/<agent_name>/`
2. Implement agent class inheriting from `BaseAgent`
3. Define `persona` and `mission` properties
4. Implement `run()` method
5. Add runner function in `src/run_agent.py`
6. Create GitHub Actions workflow
7. Update documentation

---

**System Version**: 2.0.0
**Last Updated**: February 8, 2026
**Team Lead**: Junior (juninmd)
