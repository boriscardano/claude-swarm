#!/usr/bin/env python3
"""
Simple demo runner for the E2B Hackathon.

This script coordinates multiple agents to collaboratively develop a feature
on a GitHub repository, demonstrating the power of Claude Swarm + E2B + MCPs.

Usage:
    # In each tmux pane, run:
    python run_demo.py --agent <agent-id>

Example:
    # Pane 0 (PM):        python run_demo.py --agent 0
    # Pane 1 (Backend):   python run_demo.py --agent 1
    # Pane 2 (Frontend):  python run_demo.py --agent 2
    # Pane 3 (QA):        python run_demo.py --agent 3
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from claudeswarm.messaging import AgentMessaging
from claudeswarm.discovery import AgentDiscovery
from claudeswarm.coordination import AgentCoordinator
from claudeswarm.workflows.collaborative_dev import CollaborativeDevelopmentWorkflow


async def main():
    parser = argparse.ArgumentParser(
        description="Run collaborative development demo"
    )
    parser.add_argument(
        "--agent",
        type=int,
        required=True,
        help="Agent ID (0=PM, 1=Backend, 2=Frontend, 3=QA)"
    )
    parser.add_argument(
        "--repo",
        default="https://github.com/anthropics/claude-code",
        help="GitHub repository URL"
    )
    parser.add_argument(
        "--feature",
        default="Add collaborative development workflow",
        help="Feature description"
    )
    parser.add_argument(
        "--branch",
        help="Branch name (auto-generated if not provided)"
    )
    parser.add_argument(
        "--workspace",
        default="/workspace",
        help="Workspace directory"
    )

    args = parser.parse_args()

    # Set agent ID in environment
    os.environ["CLAUDESWARM_AGENT_ID"] = f"agent-{args.agent}"

    print(f"🤖 Starting agent-{args.agent} for collaborative development demo")
    print(f"📦 Repository: {args.repo}")
    print(f"✨ Feature: {args.feature}")
    print()

    # Initialize components
    messaging = AgentMessaging()
    discovery = AgentDiscovery()
    coordinator = AgentCoordinator()

    # Create workflow
    workflow = CollaborativeDevelopmentWorkflow(
        messaging=messaging,
        discovery=discovery,
        coordinator=coordinator,
        workspace=args.workspace
    )

    # Run workflow
    try:
        result = await workflow.run_workflow(
            repo_url=args.repo,
            feature_description=args.feature,
            branch_name=args.branch
        )

        print()
        print("=" * 60)
        print("✅ Workflow completed!")
        print("=" * 60)
        print(f"Result: {result}")

        if result.get("success"):
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
