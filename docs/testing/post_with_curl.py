#!/usr/bin/env python3
"""
Script to post responses to GitHub issues using curl and a personal access token.
Requires a GitHub Personal Access Token with 'repo' scope.
"""

import subprocess
import json
import sys
import os
from pathlib import Path

# Repository info
REPO_OWNER = "brettmeyerowitz"
REPO_NAME = "homeassistant-homgar"

# Mapping of issue numbers to section headers in GITHUB_ISSUE_RESPONSES.md
ISSUES_TO_POST = {
    "9": "## Issue #11, #9, #10 - Valve Support (HTV213FRF, HTV245FRF)",
    "10": "## Issue #11, #9, #10 - Valve Support (HTV213FRF, HTV245FRF)",
    "11": "## Issue #11, #9, #10 - Valve Support (HTV213FRF, HTV245FRF)",
    "12": "## Issue #12 - HCS021FRF Unavailable",
    "2": "## Issue #2 - Disconnection",
    "4": "## Issue #4 - Device Classes and Flowmeter Decoding",
    "8": "## Issue #8 - Garbled Hub Values",
}

def get_response_content(section_header: str) -> str:
    """Extract content for a specific section from GITHUB_ISSUE_RESPONSES.md"""
    responses_file = Path("GITHUB_ISSUE_RESPONSES.md")
    if not responses_file.exists():
        print(f"Error: {responses_file} not found!")
        sys.exit(1)
    
    with open(responses_file, 'r') as f:
        content = f.read()
    
    # Find the section
    lines = content.split('\n')
    start_idx = None
    
    for i, line in enumerate(lines):
        if line.strip() == section_header:
            start_idx = i + 1  # Skip the header line
            break
    
    if start_idx is None:
        print(f"Error: Section '{section_header}' not found!")
        return ""
    
    # Extract content until next section or end of file
    response_lines = []
    for i in range(start_idx, len(lines)):
        line = lines[i]
        if line.startswith("## ") and i > start_idx:
            break  # Next section found
        response_lines.append(line)
    
    # Remove leading/trailing empty lines
    while response_lines and not response_lines[0].strip():
        response_lines.pop(0)
    while response_lines and not response_lines[-1].strip():
        response_lines.pop()
    
    return '\n'.join(response_lines)

def post_to_github_issue(issue_number: str, response: str, token: str) -> bool:
    """Post a comment to a GitHub issue using curl"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{issue_number}/comments"
    
    # Prepare the curl command
    curl_cmd = [
        'curl', '-X', 'POST',
        '-H', f'Authorization: token {token}',
        '-H', 'Accept: application/vnd.github.v3+json',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps({"body": response}),
        url
    ]
    
    try:
        result = subprocess.run(curl_cmd, capture_output=True, text=True, check=True)
        response_data = json.loads(result.stdout)
        print(f"✅ Posted response to issue #{issue_number}")
        print(f"   Comment URL: {response_data.get('html_url', 'N/A')}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to post to issue #{issue_number}: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse response for issue #{issue_number}: {e}")
        print(f"Response: {result.stdout}")
        return False

def main():
    """Main function to post all responses"""
    print("🚀 Posting responses to GitHub issues...")
    print("=" * 50)
    
    # Get token from environment variable
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("❌ GITHUB_TOKEN environment variable not set!")
        print("   Please set it: export GITHUB_TOKEN=your_personal_access_token")
        print("   Create token at: https://github.com/settings/tokens")
        print("   Token needs 'repo' scope")
        sys.exit(1)
    
    success_count = 0
    total_count = len(ISSUES_TO_POST)
    
    for issue_number, section_header in ISSUES_TO_POST.items():
        print(f"\n📝 Processing issue #{issue_number}...")
        
        # Get the response content
        response = get_response_content(section_header)
        if not response:
            print(f"⚠️  Skipping issue #{issue_number} - no content found")
            continue
        
        # Post the response
        if post_to_github_issue(issue_number, response, token):
            success_count += 1
        else:
            print(f"⚠️  Failed to post to issue #{issue_number}")
    
    print("\n" + "=" * 50)
    print(f"📊 Summary: {success_count}/{total_count} responses posted successfully!")
    
    if success_count == total_count:
        print("🎉 All responses posted successfully!")
    else:
        print("⚠️  Some responses failed. Check the errors above.")

if __name__ == "__main__":
    main()
