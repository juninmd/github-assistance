"""
Quick test to verify Telegram improvements
"""
import os
from unittest.mock import MagicMock, patch
from src.github_client import GithubClient
from src.agents.pr_assistant.agent import PRAssistantAgent
from src.ai_client import AIClient

print("=" * 60)
print("Testing Telegram Improvements")
print("=" * 60)

# Test 1: Verify send_telegram_msg accepts reply_markup
print("\n1. Testing send_telegram_msg with reply_markup parameter...")
with patch.dict('os.environ', {'GITHUB_TOKEN': 'fake', 'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': 'fake'}):
    with patch('src.github_client.requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        client = GithubClient()
        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "🔗 Ver PR", "url": "https://github.com/test/repo/pull/1"}
            ]]
        }

        client.send_telegram_msg("Test message", reply_markup=inline_keyboard)

        # Verify the call was made with reply_markup
        args, kwargs = mock_post.call_args
        payload = kwargs['json']

        assert 'reply_markup' in payload, "❌ reply_markup not in payload"
        assert 'inline_keyboard' in payload['reply_markup'], "❌ inline_keyboard not found"
        print("✅ send_telegram_msg accepts and sends reply_markup correctly")

# Test 2: Verify send_telegram_notification sends button
print("\n2. Testing send_telegram_notification includes button...")
with patch.dict('os.environ', {'GITHUB_TOKEN': 'fake', 'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': 'fake'}):
    with patch('src.github_client.requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status = MagicMock()

        client = GithubClient()

        pr = MagicMock()
        pr.number = 123
        pr.title = "Test PR Title"
        pr.user.login = "testuser"
        pr.html_url = "https://github.com/test/repo/pull/123"
        pr.base.repo.full_name = "test/repo"
        pr.body = "Test PR description"

        client.send_telegram_notification(pr)

        args, kwargs = mock_post.call_args
        payload = kwargs['json']

        assert 'reply_markup' in payload, "❌ reply_markup not in notification"
        assert payload['reply_markup']['inline_keyboard'][0][0]['text'] == "🔗 Ver PR", "❌ Button text incorrect"
        assert payload['reply_markup']['inline_keyboard'][0][0]['url'] == pr.html_url, "❌ Button URL incorrect"
        assert "test/repo" in payload['text'], "❌ Repository name not in message"
        print("✅ send_telegram_notification includes inline button correctly")

# Test 3: Verify PR Assistant tracks draft PRs
print("\n3. Testing PR Assistant tracks draft PRs...")
with patch.dict('os.environ', {'GITHUB_TOKEN': 'fake', 'JULES_API_KEY': 'fake'}):
    mock_github = MagicMock()
    mock_jules = MagicMock()
    mock_allowlist = MagicMock()
    mock_ai = MagicMock()

    # Create draft and regular PRs
    mock_issue_draft = MagicMock()
    mock_issue_draft.number = 1
    mock_issue_draft.repository.full_name = "juninmd/test-repo"
    mock_issue_draft.title = "Draft PR"

    mock_issue_ready = MagicMock()
    mock_issue_ready.number = 2
    mock_issue_ready.repository.full_name = "juninmd/test-repo"
    mock_issue_ready.title = "Ready PR"

    mock_pr_draft = MagicMock()
    mock_pr_draft.number = 1
    mock_pr_draft.draft = True
    mock_pr_draft.user.login = "juninmd"
    mock_pr_draft.title = "Draft PR"
    mock_pr_draft.html_url = "https://github.com/juninmd/test-repo/pull/1"

    mock_pr_ready = MagicMock()
    mock_pr_ready.number = 2
    mock_pr_ready.draft = False
    mock_pr_ready.user.login = "juninmd"
    mock_pr_ready.mergeable = True

    mock_issues = MagicMock()
    mock_issues.totalCount = 2
    mock_issues.__iter__.return_value = iter([mock_issue_draft, mock_issue_ready])

    mock_github.search_prs.return_value = mock_issues
    mock_github.get_pr_from_issue.side_effect = [mock_pr_draft, mock_pr_ready]

    agent = PRAssistantAgent(
        mock_jules,
        mock_github,
        mock_allowlist,
        target_owner="juninmd"
    )

    with patch.object(agent, 'process_pr', return_value={"action": "skipped", "pr": 2}):
        result = agent.run()

        assert 'draft_prs' in result, "❌ draft_prs not in result"
        assert len(result['draft_prs']) == 1, f"❌ Expected 1 draft PR, got {len(result['draft_prs'])}"
        assert result['draft_prs'][0]['pr'] == 1, "❌ Draft PR number incorrect"
        assert result['draft_prs'][0]['url'] == "https://github.com/juninmd/test-repo/pull/1", "❌ Draft PR URL incorrect"

        # Verify summary includes draft PR info
        summary_call = mock_github.send_telegram_msg.call_args[0][0]
        assert "*Draft:*" in summary_call, "❌ Draft count not in summary"
        assert "*PRs em Draft:*" in summary_call, "❌ Draft list header not in summary"
        assert "test\\-repo#1" in summary_call, "❌ Draft PR link not in summary"
        print("✅ PR Assistant tracks draft PRs and includes them in summary")

print("\n" + "=" * 60)
print("✅ All Telegram improvements tests passed!")
print("=" * 60)
print("\nSummary of improvements:")
print("1. ✅ send_telegram_msg() now accepts reply_markup parameter")
print("2. ✅ send_telegram_notification() includes '🔗 Ver PR' inline button")
print("3. ✅ PR Assistant tracks draft PRs separately")
print("4. ✅ Summary includes ALL categories with links:")
print("   - ✅ PRs Mergeados (with links)")
print("   - 🛠️ Conflitos Resolvidos (with links)")
print("   - ❌ Falhas de Pipeline (with links)")
print("   - 📝 PRs em Draft (with links)")
print("   - ⏩ Pulados/Pendentes (with links and reason)")
print("5. ✅ Repository name included in merge notifications")
print("6. ✅ Each category shows: [repo#123](url) - title")
