# AI AUDIT REMEDIATION TASK

You are assigned to remediate security and architectural findings discovered during a deep AI audit of the repository **{{repository}}**.

## Audit Findings
{{findings}}

## Target Criticality
**{{criticality}}**

## Instructions
1. Review the findings above and the relevant files in the repository.
2. Implement fixes, mitigations, or improvements for each finding.
3. Prioritize high-criticality items first.
4. Ensure all changes adhere to clean code principles and the project's architecture.
5. Verify that your changes do not introduce regressions.

### 🧪 Test Generation Requirement (MANDATORY)
- **You MUST write corresponding unit tests** (or integration tests) for any new files, classes, methods, functions, or modifications implemented.
- If code is added or modified, corresponding tests must cover all new logical branches and edge cases. Do not complete the task or create a Pull Request without adding/updating tests.
- Ensure test coverage target is met (aim for 100% test coverage for the changes, minimum 80%+ overall for the modified files).

## Deliverables
- A set of code changes addressing the audit findings.
- Corresponding unit/integration tests for all new or modified code logic.
- A summary of the remediations performed and the tests added/run in the Pull Request description.
