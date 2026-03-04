The problem: The PR Assistant skips processing PRs if `mergeable is None` ("mergeability_unknown"). The user wants to change this behavior so that if mergeability is unknown, the PR Assistant should attempt to merge it anyway to collect the real status, and handle cases where there are no pipeline actions. We should also improve log messages for this case.

Here is the plan:
1. Update `src/agents/pr_assistant/agent.py`. In `process_pr`, replace the block that skips `mergeable is None` to just log that mergeability is unknown and proceed to check pipeline status.
```python
<<<<<<< SEARCH
        # Safety Check: Verify Mergeability
        if pr.mergeable is False:
            self.log(f"PR #{pr.number} has conflicts")
            return self.handle_conflicts(pr)
        elif pr.mergeable is None:
            self.log(f"PR #{pr.number} mergeability unknown")
            return {"action": "skipped", "pr": pr.number, "reason": "mergeability_unknown"}

        # Check Pipeline Status
=======
        # Safety Check: Verify Mergeability
        if pr.mergeable is False:
            self.log(f"PR #{pr.number} has conflicts")
            return self.handle_conflicts(pr)
        elif pr.mergeable is None:
            self.log(f"PR #{pr.number} mergeability is unknown. Proceeding to check pipeline and attempt merge to collect real status.")

        # Check Pipeline Status
>>>>>>> REPLACE
```
2. Update the tests. I need to modify `tests/test_pr_assistant_gaps.py` around line 42, which specifically checks for the `"mergeability_unknown"` return reason. I will change this test to verify that when `mergeable is None`, the code proceeds to check the pipeline and merge (which can be mocked to return a successful merge, or fail due to merge).
```python
<<<<<<< SEARCH
         def test_process_pr_mergeability_none(self):
             """Test process_pr when mergeable is None."""
             pr = MagicMock()
             pr.user.login = "juninmd"
             pr.base.repo.full_name = "test/repo"
             pr.mergeable = None

             self.agent.is_pr_too_young = MagicMock(return_value=False)

             result = self.agent.process_pr(pr)

             self.assertEqual(result["action"], "skipped")
             self.assertEqual(result["reason"], "mergeability_unknown")
=======
         def test_process_pr_mergeability_none(self):
             """Test process_pr when mergeable is None. Should proceed to merge."""
             pr = MagicMock()
             pr.user.login = "juninmd"
             pr.base.repo.full_name = "test/repo"
             pr.mergeable = None

             self.agent.is_pr_too_young = MagicMock(return_value=False)
             self.agent.check_pipeline_status = MagicMock(return_value={"success": True})
             self.agent.github_client.merge_pr = MagicMock(return_value=(True, "Success"))

             result = self.agent.process_pr(pr)

             self.assertEqual(result["action"], "merged")
>>>>>>> REPLACE
```
3. Check if there are other tests covering `mergeability_unknown`. Use `uv run pytest --cov=src --cov=scripts --cov-report=term-missing` to verify the codebase after the changes.
4. Review logs and logic. If there are no commits or checks, `check_pipeline_status` returns `success: False` for `no_commits` but `success: True` if there are commits but no actions. We don't need to change `check_pipeline_status`, it already behaves correctly when there are commits but no actions (`return {"success": True}`). Wait, let me review `check_pipeline_status` just to be absolutely sure. Let's look at `agent.py` again.
If no checks exist: `check_runs` is empty, loop skips. Then `if failed_checks:` is skipped, `if pending_checks:` is skipped. `return {"success": True}`. This is perfect. What if the legacy status is neutral or empty? The legacy status block:
```python
            combined = last_commit.get_combined_status()
            if combined.state not in ['success', 'neutral'] and combined.total_count > 0:
```
If there are no legacy statuses, `combined.total_count == 0`, so it skips the block. Perfect.
5. Complete pre-commit step using `pre_commit_instructions` tool to run linting and format checks, and verify test coverage.
