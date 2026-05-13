from unittest.mock import MagicMock, patch
import pytest
from src.agents.intelligence_standardizer.agent import IntelligenceStandardizerAgent

@pytest.fixture
def mock_agent():
    return IntelligenceStandardizerAgent(
        jules_client=MagicMock(),
        github_client=MagicMock(),
        allowlist=MagicMock(),
        telegram=MagicMock(),
        target_owner="test_owner"
    )

def test_analyze_intelligence_missing_all(mock_agent):
    repo = MagicMock()
    repo.get_contents.side_effect = Exception("Not found") # Simplification of UnknownObjectException for test
    
    # We need to import UnknownObjectException to mock it correctly if we want precise test
    from github.GithubException import UnknownObjectException
    repo.get_contents.side_effect = UnknownObjectException(404, "Not found")
    
    analysis = mock_agent._analyze_intelligence(repo)
    assert analysis["missing_agents_md"] is True
    assert analysis["missing_agents_dir"] is True

def test_analyze_intelligence_present_all(mock_agent):
    repo = MagicMock()
    repo.get_contents.return_value = "content"
    
    analysis = mock_agent._analyze_intelligence(repo)
    assert analysis["missing_agents_md"] is False
    assert analysis["missing_agents_dir"] is False

@patch("src.agents.intelligence_standardizer.agent.IntelligenceStandardizerAgent.load_jules_instructions")
@patch("src.agents.intelligence_standardizer.agent.IntelligenceStandardizerAgent.create_jules_session")
def test_process_repository_triggers_session(mock_create, mock_load, mock_agent):
    repo = MagicMock()
    repo.full_name = "owner/repo"
    repo.name = "repo"
    repo.default_branch = "main"
    
    mock_agent._analyze_intelligence = MagicMock(return_value={
        "missing_agents_md": True,
        "missing_agents_dir": False,
        "missing_standard_workflow": False,
        "missing_contributing": False,
        "missing_license": False,
    })
    mock_agent.has_recent_jules_session = MagicMock(return_value=False)
    mock_load.return_value = "instructions"
    mock_create.return_value = {"id": "session_id"}
    
    results = {"processed": [], "skipped": [], "failed": []}
    mock_agent._process_repository(repo, results)
    
    assert len(results["processed"]) == 1
    assert results["processed"][0]["repository"] == "owner/repo"
    mock_create.assert_called_once()
