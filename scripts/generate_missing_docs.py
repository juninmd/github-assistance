import os
import requests
import json
from github import Github
from github.GithubException import UnknownObjectException

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:1b"

def generate_content(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return ""

def generate_readme_content(repo_name: str, repo_desc: str, file_context: str) -> str:
    desc = repo_desc if repo_desc else "A standard software project."
    prompt = (
        f"Generate a concise, professional README.md for a repository named '{repo_name}' "
        f"with the following description: '{desc}'.\n"
        f"Here is a list of existing files in the root of the repository to help you understand the project structure:\n"
        f"{file_context}\n\n"
        f"Include a short description, an installation section, and a usage section based on the files you see. "
        f"Only return the raw markdown content, no conversational text."
    )
    return generate_content(prompt)

def generate_agents_content() -> str:
    prompt = (
        "You are an AI assistant generating guidelines for an AGENTS.md file. "
        "The file acts as instructions for AI coding agents working on this repository. "
        "Generate the guidelines strictly in English. "
        "You MUST include the following principles and explicit rules:\n"
        "- DRY (Don't Repeat Yourself)\n"
        "- KISS (Keep It Simple, Stupid)\n"
        "- SOLID principles\n"
        "- YAGNI (You Aren't Gonna Need It)\n"
        "- All development must be productive. Do not use mocks or fake implementations. Use mocks ONLY for tests.\n"
        "- Each file must have a maximum of 180 lines of code.\n"
        "- Ensure at least 80% test coverage.\n\n"
        "Return ONLY the raw markdown content without any conversational filler."
    )
    return generate_content(prompt)

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN is not set.")
        return

    g = Github(token)
    user = g.get_user()
    
    # We use affiliation='owner' to avoid changing organization repos unless specified
    # Using visibility='all' gets public and private
    repos = user.get_repos(affiliation='owner')

    for repo in repos:
        if repo.archived:
            continue
            
        print(f"Checking repository: {repo.full_name}")
        
        # Check README.md
        has_readme = False
        try:
            repo.get_contents("README.md")
            has_readme = True
        except UnknownObjectException:
            # File does not exist
            pass
        
        if not has_readme:
            print(f"  -> README.md is missing. Generating...")
            
            # Get list of files in the root directory for context
            file_context = "No files found."
            try:
                contents = repo.get_contents("")
                if isinstance(contents, list):
                    file_context = "\n".join([f"- {c.path}" for c in contents if c.path])
            except UnknownObjectException:
                pass
            except Exception as e:
                print(f"  -> Warning: failed to fetch repository contents: {e}")

            content = generate_readme_content(repo.name, repo.description, file_context)
            if content:
                try:
                    repo.create_file(
                        path="README.md",
                        message="docs: create README.md via AI",
                        content=content,
                        branch=repo.default_branch
                    )
                    print("  -> Successfully created README.md")
                except Exception as e:
                    print(f"  -> Failed to create README.md: {e}")
            else:
                print("  -> Ollama returned empty content for README.md.")

        # Check AGENTS.md
        has_agents = False
        try:
            repo.get_contents("AGENTS.md")
            has_agents = True
        except UnknownObjectException:
            pass

        if not has_agents:
            print(f"  -> AGENTS.md is missing. Generating...")
            content = generate_agents_content()
            if content:
                try:
                    repo.create_file(
                        path="AGENTS.md",
                        message="docs: create AGENTS.md via AI",
                        content=content,
                        branch=repo.default_branch
                    )
                    print("  -> Successfully created AGENTS.md")
                except Exception as e:
                    print(f"  -> Failed to create AGENTS.md: {e}")
            else:
                print("  -> Ollama returned empty content for AGENTS.md.")

if __name__ == "__main__":
    main()
