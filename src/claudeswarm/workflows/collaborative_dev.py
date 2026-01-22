"""
Collaborative Development Workflow

Multi-agent workflow for collaborative feature development:
1. Agent 1 (PM): Clones repo, analyzes codebase, creates task breakdown
2. Agent 2 (Backend): Implements backend changes
3. Agent 3 (Frontend): Implements frontend changes
4. Agent 4 (QA): Writes tests, validates, commits & pushes

This workflow showcases true multi-agent coordination for the E2B hackathon.
"""

import json
import os
import asyncio
from typing import Dict, List, Optional, Any
from pathlib import Path

from ..messaging import AgentMessaging
from ..discovery import AgentDiscovery
from ..coordination import AgentCoordinator


class CollaborativeDevelopmentWorkflow:
    """
    Coordinates multiple agents to collaboratively develop a new feature.

    This workflow demonstrates:
    - Task delegation and coordination
    - Parallel work (backend + frontend)
    - Git operations via MCP
    - Multi-agent synchronization
    """

    def __init__(
        self,
        messaging: AgentMessaging,
        discovery: AgentDiscovery,
        coordinator: AgentCoordinator,
        workspace: str = "/workspace"
    ):
        self.messaging = messaging
        self.discovery = discovery
        self.coordinator = coordinator
        self.workspace = workspace
        self.agent_id = os.getenv("CLAUDESWARM_AGENT_ID", "agent-0")

    async def run_workflow(
        self,
        repo_url: str,
        feature_description: str,
        branch_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute the collaborative development workflow.

        Args:
            repo_url: GitHub repository URL to clone
            feature_description: Description of the feature to implement
            branch_name: Optional branch name (auto-generated if not provided)

        Returns:
            Dictionary with workflow results including commit hash and PR URL
        """
        if not branch_name:
            # Generate branch name from feature description
            branch_name = f"feature/{feature_description[:30].lower().replace(' ', '-')}"

        # Determine agent role based on agent ID
        agent_roles = {
            "agent-0": "project-manager",
            "agent-1": "backend-developer",
            "agent-2": "frontend-developer",
            "agent-3": "qa-engineer"
        }
        role = agent_roles.get(self.agent_id, "developer")

        print(f"🤖 Agent {self.agent_id} starting as {role}")

        # Execute role-specific tasks
        if role == "project-manager":
            return await self._run_project_manager(repo_url, feature_description, branch_name)
        elif role == "backend-developer":
            return await self._run_backend_developer(feature_description)
        elif role == "frontend-developer":
            return await self._run_frontend_developer(feature_description)
        elif role == "qa-engineer":
            return await self._run_qa_engineer(branch_name)
        else:
            return await self._run_generic_developer(feature_description)

    async def _run_project_manager(
        self,
        repo_url: str,
        feature_description: str,
        branch_name: str
    ) -> Dict[str, Any]:
        """
        Project Manager: Clone repo, analyze, and coordinate task distribution.
        """
        print("📋 [PM] Starting project management tasks...")

        # Step 1: Clone repository
        print(f"📦 [PM] Cloning repository: {repo_url}")
        clone_result = await self._clone_repository(repo_url)

        if not clone_result["success"]:
            return {"success": False, "error": "Failed to clone repository"}

        repo_path = clone_result["path"]

        # Step 2: Analyze codebase structure
        print("🔍 [PM] Analyzing codebase structure...")
        analysis = await self._analyze_codebase(repo_path)

        # Step 3: Create task breakdown
        print("📝 [PM] Creating task breakdown...")
        tasks = await self._create_task_breakdown(analysis, feature_description)

        # Step 4: Broadcast tasks to other agents
        print("📢 [PM] Broadcasting tasks to agents...")
        await self.messaging.broadcast({
            "type": "task_assignment",
            "feature": feature_description,
            "branch": branch_name,
            "repo_path": repo_path,
            "tasks": tasks,
            "analysis": analysis
        })

        # Step 5: Wait for agents to complete their tasks
        print("⏳ [PM] Waiting for agents to complete tasks...")
        completion_status = await self._wait_for_task_completion(tasks)

        return {
            "success": True,
            "role": "project-manager",
            "tasks_created": len(tasks),
            "completion_status": completion_status,
            "repo_path": repo_path
        }

    async def _run_backend_developer(self, feature_description: str) -> Dict[str, Any]:
        """
        Backend Developer: Implement backend changes.
        """
        print("⚙️  [Backend] Starting backend development...")

        # Wait for task assignment from PM
        print("📨 [Backend] Waiting for task assignment...")
        task_msg = await self._wait_for_message("task_assignment")

        if not task_msg:
            return {"success": False, "error": "No task assignment received"}

        repo_path = task_msg["repo_path"]
        backend_tasks = [t for t in task_msg["tasks"] if t["role"] == "backend"]

        print(f"📝 [Backend] Received {len(backend_tasks)} tasks")

        # Implement backend changes
        changes_made = []
        for task in backend_tasks:
            print(f"🔨 [Backend] Working on: {task['description']}")
            result = await self._implement_backend_task(repo_path, task)
            changes_made.append(result)

        # Notify PM of completion
        await self.messaging.broadcast({
            "type": "task_completed",
            "role": "backend",
            "changes": changes_made
        })

        print("✅ [Backend] Backend tasks completed!")

        return {
            "success": True,
            "role": "backend-developer",
            "changes_made": len(changes_made)
        }

    async def _run_frontend_developer(self, feature_description: str) -> Dict[str, Any]:
        """
        Frontend Developer: Implement frontend changes.
        """
        print("🎨 [Frontend] Starting frontend development...")

        # Wait for task assignment from PM
        print("📨 [Frontend] Waiting for task assignment...")
        task_msg = await self._wait_for_message("task_assignment")

        if not task_msg:
            return {"success": False, "error": "No task assignment received"}

        repo_path = task_msg["repo_path"]
        frontend_tasks = [t for t in task_msg["tasks"] if t["role"] == "frontend"]

        print(f"📝 [Frontend] Received {len(frontend_tasks)} tasks")

        # Implement frontend changes
        changes_made = []
        for task in frontend_tasks:
            print(f"🔨 [Frontend] Working on: {task['description']}")
            result = await self._implement_frontend_task(repo_path, task)
            changes_made.append(result)

        # Notify PM of completion
        await self.messaging.broadcast({
            "type": "task_completed",
            "role": "frontend",
            "changes": changes_made
        })

        print("✅ [Frontend] Frontend tasks completed!")

        return {
            "success": True,
            "role": "frontend-developer",
            "changes_made": len(changes_made)
        }

    async def _run_qa_engineer(self, branch_name: str) -> Dict[str, Any]:
        """
        QA Engineer: Write tests, validate, commit, and push.
        """
        print("🧪 [QA] Starting QA tasks...")

        # Wait for all developers to complete
        print("📨 [QA] Waiting for development completion...")
        await self._wait_for_all_developers()

        task_msg = await self._wait_for_message("task_assignment")
        if not task_msg:
            return {"success": False, "error": "No task assignment received"}

        repo_path = task_msg["repo_path"]

        # Write tests
        print("📝 [QA] Writing tests...")
        test_results = await self._write_tests(repo_path, task_msg["feature"])

        # Run tests
        print("🧪 [QA] Running tests...")
        test_passed = await self._run_tests(repo_path)

        if not test_passed:
            print("❌ [QA] Tests failed! Notifying team...")
            await self.messaging.broadcast({
                "type": "test_failed",
                "message": "Tests failed, please review changes"
            })
            return {"success": False, "error": "Tests failed"}

        # Commit changes
        print("💾 [QA] Committing changes...")
        commit_result = await self._commit_changes(
            repo_path,
            f"feat: {task_msg['feature']}\n\nImplemented by Claude Swarm multi-agent system"
        )

        # Push to origin
        print("🚀 [QA] Pushing to origin...")
        push_result = await self._push_changes(repo_path, branch_name)

        # Notify completion
        await self.messaging.broadcast({
            "type": "workflow_completed",
            "commit": commit_result,
            "branch": branch_name,
            "tests_passed": True
        })

        print("✅ [QA] All QA tasks completed!")

        return {
            "success": True,
            "role": "qa-engineer",
            "tests_written": test_results["count"],
            "tests_passed": True,
            "commit_hash": commit_result.get("hash"),
            "branch": branch_name
        }

    async def _run_generic_developer(self, feature_description: str) -> Dict[str, Any]:
        """
        Generic developer role for extra agents.
        """
        print("👨‍💻 [Developer] Starting development tasks...")

        # Wait for task assignment
        task_msg = await self._wait_for_message("task_assignment")
        if not task_msg:
            return {"success": False, "error": "No task assignment received"}

        print("✅ [Developer] Ready to assist!")

        return {"success": True, "role": "developer", "status": "ready"}

    # Helper methods for actual implementation

    async def _clone_repository(self, repo_url: str) -> Dict[str, Any]:
        """Clone repository using git command."""
        repo_name = repo_url.split("/")[-1].replace(".git", "")

        # Validate repo path stays within workspace (prevent path traversal)
        workspace_path = Path(self.workspace).resolve()
        repo_path = (workspace_path / repo_name).resolve()

        # Ensure repo_path is within workspace
        try:
            repo_path.relative_to(workspace_path)
        except ValueError:
            return {"success": False, "error": "Invalid repository path - path traversal attempt detected"}

        # Use git command to clone
        # In real implementation, this would use GitHub MCP
        # For now, using shell command as placeholder
        try:
            # Use create_subprocess_exec instead of create_subprocess_shell to prevent command injection
            process = await asyncio.create_subprocess_exec(
                "git", "clone", repo_url, str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            return {
                "success": process.returncode == 0,
                "path": str(repo_path)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _analyze_codebase(self, repo_path: str) -> Dict[str, Any]:
        """Analyze codebase structure."""
        analysis = {
            "languages": [],
            "directories": [],
            "key_files": [],
            "structure": {}
        }

        # Walk through repository
        path_obj = Path(repo_path)
        if path_obj.exists():
            # Detect languages
            extensions = set()
            for file in path_obj.rglob("*"):
                if file.is_file() and not any(part.startswith(".") for part in file.parts):
                    extensions.add(file.suffix)

            # Map extensions to languages
            lang_map = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".jsx": "React",
                ".tsx": "React TypeScript",
                ".go": "Go",
                ".rs": "Rust",
                ".java": "Java"
            }
            analysis["languages"] = list(set(lang_map.get(ext, ext) for ext in extensions if ext in lang_map))

            # Find key directories
            analysis["directories"] = [
                d.name for d in path_obj.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]

        return analysis

    async def _create_task_breakdown(
        self,
        analysis: Dict[str, Any],
        feature_description: str
    ) -> List[Dict[str, Any]]:
        """Create task breakdown based on codebase analysis."""
        tasks = []

        # Determine if we need backend/frontend split
        languages = analysis.get("languages", [])
        has_frontend = any(lang in ["JavaScript", "TypeScript", "React", "React TypeScript"] for lang in languages)
        has_backend = any(lang in ["Python", "Go", "Rust", "Java"] for lang in languages)

        if has_backend:
            tasks.append({
                "role": "backend",
                "description": f"Implement backend logic for: {feature_description}",
                "priority": 1
            })

        if has_frontend:
            tasks.append({
                "role": "frontend",
                "description": f"Implement UI for: {feature_description}",
                "priority": 1
            })

        # Always add testing task
        tasks.append({
            "role": "qa",
            "description": f"Write tests for: {feature_description}",
            "priority": 2
        })

        return tasks

    async def _implement_backend_task(
        self,
        repo_path: str,
        task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Implement a backend task."""
        # Placeholder: In real implementation, this would use Claude to generate code
        return {
            "task": task["description"],
            "files_modified": [],
            "status": "completed"
        }

    async def _implement_frontend_task(
        self,
        repo_path: str,
        task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Implement a frontend task."""
        # Placeholder: In real implementation, this would use Claude to generate code
        return {
            "task": task["description"],
            "files_modified": [],
            "status": "completed"
        }

    async def _write_tests(
        self,
        repo_path: str,
        feature: str
    ) -> Dict[str, Any]:
        """Write tests for the feature."""
        # Placeholder
        return {"count": 0, "files": []}

    async def _run_tests(self, repo_path: str) -> bool:
        """Run test suite."""
        # Placeholder
        return True

    async def _commit_changes(
        self,
        repo_path: str,
        message: str
    ) -> Dict[str, Any]:
        """Commit changes using git."""
        try:
            # Git add
            process = await asyncio.create_subprocess_shell(
                f"cd {repo_path} && git add .",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # Git commit
            process = await asyncio.create_subprocess_shell(
                f'cd {repo_path} && git commit -m "{message}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            # Extract commit hash
            commit_hash = stdout.decode().split()[1] if process.returncode == 0 else None

            return {
                "success": process.returncode == 0,
                "hash": commit_hash
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _push_changes(
        self,
        repo_path: str,
        branch: str
    ) -> Dict[str, Any]:
        """Push changes to origin."""
        try:
            process = await asyncio.create_subprocess_shell(
                f"cd {repo_path} && git push origin {branch}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            return {"success": process.returncode == 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _wait_for_message(
        self,
        message_type: str,
        timeout: int = 60
    ) -> Optional[Dict[str, Any]]:
        """Wait for a specific message type."""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = self.messaging.receive()
            for msg in messages:
                if msg.get("type") == message_type:
                    return msg
            await asyncio.sleep(0.5)

        return None

    async def _wait_for_all_developers(self, timeout: int = 120) -> bool:
        """Wait for all developers to complete their tasks."""
        completed_roles = set()
        required_roles = {"backend", "frontend"}

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = self.messaging.receive()
            for msg in messages:
                if msg.get("type") == "task_completed":
                    completed_roles.add(msg.get("role"))

            if required_roles.issubset(completed_roles):
                return True

            await asyncio.sleep(0.5)

        return False

    async def _wait_for_task_completion(
        self,
        tasks: List[Dict[str, Any]],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """Wait for all tasks to complete."""
        completed_tasks = set()
        required_roles = {task["role"] for task in tasks}

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = self.messaging.receive()
            for msg in messages:
                if msg.get("type") == "task_completed":
                    completed_tasks.add(msg.get("role"))

            if required_roles.issubset(completed_tasks):
                return {
                    "all_completed": True,
                    "completed_roles": list(completed_tasks)
                }

            await asyncio.sleep(1.0)

        return {
            "all_completed": False,
            "completed_roles": list(completed_tasks),
            "missing_roles": list(required_roles - completed_tasks)
        }
