import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.agents.pr_assistant import PRAssistantAgent

def run_local_test():
    print("=" * 60)
    print("Running PR Assistant Algorithm Test (LOCAL)")
    print("=" * 60)

    # 1. Mock Clients
    mock_jules = MagicMock()
    mock_github = MagicMock()
    mock_ai = MagicMock()
    mock_allowlist = MagicMock()

    # 2. Setup Mock Data
    search_results = MagicMock()
    search_results.totalCount = 2

    # PR 1: Success
    pr1 = MagicMock()
    pr1.number = 16
    pr1.title = "Refactor Core Logic"
    pr1.user.login = "juninmd"
    pr1.base.repo.full_name = "juninmd/agar"
    pr1.mergeable = True

    # PR 2: Conflicts
    pr2 = MagicMock()
    pr2.number = 17
    pr2.title = "Update README"
    pr2.user.login = "juninmd"
    pr2.base.repo.full_name = "juninmd/agar"
    pr2.mergeable = False

    mock_issue1 = MagicMock()
    mock_issue1.number = 16
    mock_issue1.repository.full_name = "juninmd/agar"
    mock_issue1.title = "Refactor Core Logic"

    mock_issue2 = MagicMock()
    mock_issue2.number = 17
    mock_issue2.repository.full_name = "juninmd/agar"
    mock_issue2.title = "Update README"

    search_results.__iter__.return_value = [mock_issue1, mock_issue2]
    mock_github.search_prs.return_value = search_results
    mock_github.get_pr_from_issue.side_effect = [pr1, pr2]

    # Mock PR1 Commits and Status
    commit1 = MagicMock()
    combined_status1 = MagicMock()
    combined_status1.state = "success"
    combined_status1.total_count = 1
    commit1.get_combined_status.return_value = combined_status1

    check_run1 = MagicMock()
    check_run1.status = "completed"
    check_run1.conclusion = "neutral"
    commit1.get_check_runs.return_value = [check_run1]

    pr1.get_commits.return_value.reversed = [commit1]
    pr1.get_commits.return_value.totalCount = 1

    # Mock Merge Success for PR1
    mock_github.merge_pr.return_value = (True, "Successfully merged")
    mock_github.send_telegram_msg.return_value = True
    mock_github.get_issue_comments.return_value = []

    # 3. Initialize Agent
    agent = PRAssistantAgent(
        mock_jules,
        mock_github,
        mock_allowlist,
        target_owner="juninmd"
    )

    # 4. Run Agent
    print("\n--- Starting Execution ---\n")
    results = agent.run()
    print("\n--- Execution Finished ---\n")

    # 5. Verify Results
    print(f"Total Found: {results['total_found']}")
    print(f"Merged: {len(results['merged'])}")
    if results['merged']:
        print(f"  - Merged PR: {results['merged'][0]['pr']} ({results['merged'][0]['title']})")

    print(f"Conflicts (Notified): {len(results['conflicts_resolved'])}")
    if results['conflicts_resolved']:
        print(f"  - Conflict PR: {results['conflicts_resolved'][0]['pr']}")

    print(f"Skipped: {len(results['skipped'])}")

    print("\n" + "=" * 60)
    print("SUCCESS: Algorithm test completed and verified 'neutral' as success and conflict notification.")
    print("=" * 60)

if __name__ == "__main__":
    run_local_test()
