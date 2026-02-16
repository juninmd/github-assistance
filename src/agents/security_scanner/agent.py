"""
Security Scanner Agent - Scans GitHub repositories for exposed secrets using gitleaks.
"""
import json
import os
import subprocess
import tempfile
from typing import Dict, Any, List
from datetime import datetime
from urllib.parse import quote
from src.agents.base_agent import BaseAgent


class SecurityScannerAgent(BaseAgent):
    """
    Security Scanner Agent
    
    Scans all GitHub repositories for exposed credentials using gitleaks.
    Sends sanitized reports to Telegram without revealing actual secret values.
    """

    @property
    def persona(self) -> str:
        """Load persona from instructions.md"""
        return self.get_instructions_section("## Persona")

    @property
    def mission(self) -> str:
        """Load mission from instructions.md"""
        return self.get_instructions_section("## Mission")

    def __init__(
        self,
        *args,
        target_owner: str = "juninmd",
        **kwargs
    ):
        """
        Initialize Security Scanner Agent.

        Args:
            target_owner: GitHub username to scan repositories for
        """
        super().__init__(*args, name="security_scanner", **kwargs)
        self.target_owner = target_owner

    def _escape_telegram(self, text: str) -> str:
        """
        Escape special characters for Telegram MarkdownV2.
        For MarkdownV2, we need to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
        """
        if not text:
            return text
        special_chars = ['\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def _ensure_gitleaks_installed(self) -> bool:
        """
        Check if gitleaks is installed, install if not.
        
        Returns:
            True if gitleaks is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["gitleaks", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.log(f"Gitleaks is installed: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        self.log("Gitleaks not found, attempting to install...")
        try:
            # Install gitleaks using their official installation script
            install_script = """
            cd /tmp
            wget -q https://github.com/gitleaks/gitleaks/releases/download/v8.18.1/gitleaks_8.18.1_linux_x64.tar.gz
            tar xzf gitleaks_8.18.1_linux_x64.tar.gz
            sudo mv gitleaks /usr/local/bin/
            sudo chmod +x /usr/local/bin/gitleaks
            """
            
            result = subprocess.run(
                install_script,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.log("Gitleaks installed successfully")
                return True
            else:
                # Don't log stderr to avoid potential sensitive data
                self.log("Failed to install gitleaks", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"Error installing gitleaks: {type(e).__name__}", "ERROR")
            return False

    def _scan_repository(self, repo_name: str, default_branch: str = "main") -> Dict[str, Any]:
        """
        Scan a single repository for secrets using gitleaks.
        
        Args:
            repo_name: Full repository name (owner/repo)
            default_branch: Default branch of the repository
            
        Returns:
            Dictionary with scan results
        """
        self.log(f"Scanning repository: {repo_name}")
        
        result = {
            "repository": repo_name,
            "default_branch": default_branch,
            "findings": [],
            "error": None,
            "scanned": False
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Get GitHub token
                token = os.getenv("GITHUB_TOKEN")
                if not token:
                    result["error"] = "GITHUB_TOKEN not available"
                    return result
                
                # Clone repository
                repo_url = f"https://x-access-token:{token}@github.com/{repo_name}.git"
                clone_dir = os.path.join(temp_dir, "repo")
                
                self.log(f"Cloning {repo_name}...")
                clone_result = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, clone_dir],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if clone_result.returncode != 0:
                    # Don't include full stderr as it might contain URL with token
                    # Git clone errors may expose the repository URL which contains the access token
                    result["error"] = f"Clone failed with exit code {clone_result.returncode}"
                    return result
                
                # Run gitleaks scan
                report_file = os.path.join(temp_dir, "gitleaks-report.json")
                self.log(f"Running gitleaks scan on {repo_name}...")
                
                gitleaks_result = subprocess.run(
                    [
                        "gitleaks",
                        "detect",
                        "--source", clone_dir,
                        "--report-path", report_file,
                        "--report-format", "json"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                # Gitleaks returns exit code 1 if leaks are found, 0 if no leaks
                # We only treat other exit codes as errors
                if gitleaks_result.returncode not in [0, 1]:
                    # Don't include stderr as it might contain sensitive data
                    result["error"] = f"Gitleaks scan failed with exit code {gitleaks_result.returncode}"
                    return result
                
                # Parse results if report file exists
                if os.path.exists(report_file):
                    with open(report_file, 'r') as f:
                        try:
                            findings = json.load(f)
                            # Fix: Strip local temp path from file paths
                            for finding in findings:
                                if "File" in finding and finding["File"].startswith(clone_dir):
                                    finding["File"] = os.path.relpath(finding["File"], start=clone_dir)
                            # Sanitize findings - remove actual secret values
                            result["findings"] = self._sanitize_findings(findings)
                        except json.JSONDecodeError as e:
                            result["error"] = f"Failed to parse gitleaks report: {e}"
                            return result
                
                result["scanned"] = True
                self.log(f"Scan completed for {repo_name}: {len(result['findings'])} findings")
                
            except subprocess.TimeoutExpired:
                result["error"] = "Scan timeout exceeded"
            except Exception as e:
                result["error"] = f"Scan error: {str(e)}"
                self.log(f"Error scanning {repo_name}: {e}", "ERROR")
        
        return result

    def _sanitize_findings(self, findings: List[Dict]) -> List[Dict]:
        """
        Sanitize gitleaks findings to remove actual secret values.
        
        Args:
            findings: Raw gitleaks findings
            
        Returns:
            Sanitized findings with metadata only
        """
        sanitized = []
        
        for finding in findings:
            # Extract only safe metadata
            sanitized_finding = {
                "rule_id": finding.get("RuleID", "unknown"),
                "description": finding.get("Description", ""),
                "file": finding.get("File", ""),
                "line": finding.get("StartLine", 0),
                "commit": finding.get("Commit", "")[:8],  # Short commit hash
                "author": finding.get("Author", ""),
                "date": finding.get("Date", ""),
                # NEVER include: Secret, Match, or any actual credential data
            }
            sanitized.append(sanitized_finding)
        
        return sanitized

    def _get_all_repositories(self) -> List[Dict[str, str]]:
        """
        Get all repositories owned by the target user.
        
        Returns:
            List of dictionaries with repository full names and default branches
        """
        try:
            user = self.github_client.g.get_user(self.target_owner)
            repos = []
            
            for repo in user.get_repos():
                # Only include repos owned by the user (not forks from other users)
                if repo.owner.login == self.target_owner:
                    repos.append({
                        "name": repo.full_name,
                        "default_branch": repo.default_branch
                    })
            
            self.log(f"Found {len(repos)} repositories for {self.target_owner}")
            return repos
            
        except Exception as e:
            self.log(f"Error fetching repositories: {e}", "ERROR")
            return []

    def run(self) -> Dict[str, Any]:
        """
        Execute Security Scanner workflow:
        1. Ensure gitleaks is installed
        2. Get all repositories for target owner
        3. Scan each repository
        4. Generate and send sanitized report via Telegram
        
        Returns:
            Summary of scan results
        """
        self.log("Starting Security Scanner workflow")
        self.log(f"Target owner: {self.target_owner}")
        
        results = {
            "total_repositories": 0,
            "scanned": 0,
            "failed": 0,
            "total_findings": 0,
            "all_repositories": [],
            "repositories_with_findings": [],
            "scan_errors": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Ensure gitleaks is installed
        if not self._ensure_gitleaks_installed():
            error_msg = "Failed to install gitleaks. Cannot proceed with security scan."
            self.log(error_msg, "ERROR")
            results["error"] = error_msg
            self._send_error_notification(error_msg)
            return results
        
        # Get all repositories
        repositories = self._get_all_repositories()
        results["total_repositories"] = len(repositories)
        results["all_repositories"] = repositories
        
        if not repositories:
            self.log("No repositories found to scan")
            self._send_notification(results)
            return results
        
        # Scan each repository
        for repo_info in repositories:
            repo_name = repo_info["name"]
            default_branch = repo_info["default_branch"]
            try:
                scan_result = self._scan_repository(repo_name, default_branch)
                
                if scan_result["scanned"]:
                    results["scanned"] += 1
                    
                    if scan_result["findings"]:
                        results["total_findings"] += len(scan_result["findings"])
                        results["repositories_with_findings"].append({
                            "repository": repo_name,
                            "default_branch": default_branch,
                            "findings": scan_result["findings"]
                        })
                else:
                    results["failed"] += 1
                    if scan_result["error"]:
                        results["scan_errors"].append({
                            "repository": repo_name,
                            "error": scan_result["error"]
                        })
                        
            except Exception as e:
                self.log(f"Unexpected error scanning {repo_name}: {e}", "ERROR")
                results["failed"] += 1
                results["scan_errors"].append({
                    "repository": repo_name,
                    "error": str(e)
                })
        
        self.log(f"Scan completed: {results['scanned']} scanned, "
                f"{results['failed']} failed, {results['total_findings']} findings")
        
        # Send Telegram notification
        self._send_notification(results)
        
        return results

    def _send_notification(self, results: Dict[str, Any]):
        """
        Send sanitized security scan report to Telegram.
        
        Args:
            results: Scan results dictionary
        """
        MAX_TELEGRAM_LENGTH = 3800

        # Prepare content lines
        lines = []

        # 1. Header
        header_text = (
            "🔐 *Relatório do Security Scanner*\n\n"
            f"📊 *Repos escaneados:* {results['scanned']}/{results['total_repositories']}\n"
            f"❌ *Erros de scan:* {results['failed']}\n"
            f"⚠️ *Total de achados:* {results['total_findings']}\n"
            f"📦 *Repos com problemas:* {len(results['repositories_with_findings'])}\n"
            f"👤 Dono: `{self._escape_telegram(self.target_owner)}`"
        )
        lines.append(header_text)
        
        # 2. List of ALL Repositories
        if results.get('all_repositories'):
            lines.append("\n📦 *Todos os Repositórios:*")

            # Determine status for each repo
            dirty_repos = {r['repository'] for r in results['repositories_with_findings']}
            error_repos = {r['repository'] for r in results['scan_errors']}

            # Sort alphabetically
            sorted_repos = sorted(results['all_repositories'], key=lambda x: x['name'].lower())

            for repo in sorted_repos:
                name = repo['name']
                # Use full name (owner/repo) to ensure username is visible
                escaped_name = self._escape_telegram(name)

                if name in dirty_repos:
                    status = "⚠️"
                elif name in error_repos:
                    status = "❌"
                else:
                    status = "✅"

                lines.append(f"{status} {escaped_name}")

        # 3. Details of Findings (if any)
        repos_with_findings = sorted(
            results['repositories_with_findings'],
            key=lambda x: len(x['findings']),
            reverse=True
        )

        if repos_with_findings:
            lines.append("\n⚠️ *Detalhes dos Achados:*")
            
            for repo_data in repos_with_findings:
                repo_name = repo_data['repository']
                default_branch = repo_data.get('default_branch', 'main')
                findings = repo_data['findings']
                repo_short = repo_name.split('/')[-1]
                
                # Repo Header
                lines.append(f"\n*{self._escape_telegram(repo_short)}* \\({len(findings)}\\):")
                
                # Findings (limit 2 per repo)
                max_f = 2
                for finding in findings[:max_f]:
                    rule_id = self._escape_telegram(finding['rule_id'])
                    file_path = finding['file']
                    line = finding['line']
                    author = finding.get('author', 'unknown').split(' <')[0]
                    author_esc = self._escape_telegram(author)
                    
                    encoded_file_path = quote(file_path, safe='/')
                    github_url = f"https://github.com/{repo_name}/blob/{default_branch}/{encoded_file_path}#L{line}"
                    lines.append(f"  • [{rule_id}]({github_url}) @{author_esc}")
                
                if len(findings) > max_f:
                    lines.append(f"  \\+ {len(findings) - max_f} achados")

        # 4. Scan Errors (if any)
        if results['scan_errors']:
            lines.append(f"\n❌ *Erros de Scan \\({len(results['scan_errors'])}\\):*")
            for error in results['scan_errors']:
                repo_short = error['repository'].split('/')[-1]
                error_msg = error['error'][:40]
                lines.append(f"  • {self._escape_telegram(repo_short)}: {self._escape_telegram(error_msg)}")

        # 5. Send messages with pagination
        current_message = ""
        
        for i, line in enumerate(lines):
            # Check if adding this line (plus newline) exceeds limit
            # If current_message is empty, we just take the line regardless (to avoid infinite loop if line > limit)
            if current_message and len(current_message) + len(line) + 1 > MAX_TELEGRAM_LENGTH:
                self.github_client.send_telegram_msg(current_message, parse_mode="MarkdownV2")
                current_message = "⚠️ *Continuação...*\n" + line
            else:
                if current_message:
                    current_message += "\n" + line
                else:
                    current_message = line

        if current_message:
            self.github_client.send_telegram_msg(current_message, parse_mode="MarkdownV2")

    def _send_error_notification(self, error_message: str):
        """
        Send error notification to Telegram.
        
        Args:
            error_message: Error message to send
        """
        text = (
            "🔐 *Security Scanner Error*\n\n"
            f"❌ {self._escape_telegram(error_message)}\n\n"
            f"👤 Owner: `{self._escape_telegram(self.target_owner)}`"
        )
        
        self.github_client.send_telegram_msg(text, parse_mode="MarkdownV2")
