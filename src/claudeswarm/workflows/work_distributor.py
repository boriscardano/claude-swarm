"""
Work Distribution System

This module handles breaking down features into tasks and coordinating
task assignment among agents autonomously.

Key responsibilities:
- Decompose feature requests into specific tasks
- Broadcast available tasks to agents
- Track task claims and prevent double-assignment
- Monitor task progress and handle reassignment if needed

Author: agent-1
Created: 2025-11-19 (E2B Hackathon Prep)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

from claudeswarm.messaging import MessageType, MessagingSystem


@dataclass
class Task:
    """Represents a single development task"""

    id: str
    title: str
    description: str
    files: list[str]
    dependencies: list[str] = field(default_factory=list)  # Task IDs that must complete first
    agent_id: str | None = None
    status: str = "available"  # available, claimed, in_progress, completed, blocked
    created_at: datetime = field(default_factory=datetime.now)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_minutes: int = 30


class WorkDistributor:
    """
    Manages task distribution among autonomous agents.

    This class intelligently breaks down feature requests into tasks,
    broadcasts them to available agents, and tracks progress.

    Example:
        distributor = WorkDistributor(num_agents=4)
        tasks = await distributor.decompose_feature(
            "Add JWT authentication to FastAPI app",
            research_results=research_data
        )
        await distributor.broadcast_tasks(tasks)
        status = distributor.get_progress_summary()
    """

    # Maximum number of agents allowed to prevent resource exhaustion
    MAX_AGENTS = 100

    def __init__(self, num_agents: int = 4):
        if num_agents > self.MAX_AGENTS:
            raise ValueError(f"num_agents must not exceed {self.MAX_AGENTS}")
        if num_agents < 1:
            raise ValueError("num_agents must be at least 1")

        self.num_agents = num_agents
        self.tasks: dict[str, Task] = {}
        self.messaging = MessagingSystem()
        self._task_lock = Lock()  # Thread safety for task operations

    async def decompose_feature(
        self, feature_description: str, research_results: dict | None = None
    ) -> list[Task]:
        """
        Break down a feature into specific, actionable tasks.

        This uses heuristics and patterns to intelligently decompose features.
        For the hackathon demo, we focus on common web dev patterns.

        Args:
            feature_description: Natural language feature request
            research_results: Optional research findings to inform decomposition

        Returns:
            List of tasks ready for agent assignment
        """

        feature_lower = feature_description.lower()

        # Pattern matching for common feature types
        if "auth" in feature_lower or "jwt" in feature_lower:
            tasks = self._decompose_auth_feature(feature_description, research_results)
        elif "api" in feature_lower or "endpoint" in feature_lower:
            tasks = self._decompose_api_feature(feature_description, research_results)
        elif "database" in feature_lower or "model" in feature_lower:
            tasks = self._decompose_database_feature(feature_description, research_results)
        elif "ui" in feature_lower or "frontend" in feature_lower:
            tasks = self._decompose_ui_feature(feature_description, research_results)
        else:
            tasks = self._decompose_generic_feature(feature_description, research_results)

        # Store tasks
        for task in tasks:
            self.tasks[task.id] = task

        return tasks

    def _decompose_auth_feature(
        self, feature_description: str, research_results: dict | None
    ) -> list[Task]:
        """Decompose authentication-related features"""

        # Extract recommendations from research if available
        use_argon2 = False
        use_rs256 = False
        if research_results:
            best_practices = research_results.get("best_practices", [])
            use_argon2 = any("argon2" in bp.lower() for bp in best_practices)
            use_rs256 = any("rs256" in bp.lower() for bp in best_practices)

        tasks = [
            Task(
                id="auth-task-1",
                title="Implement user model with password hashing",
                description=f"Create User model with {'argon2' if use_argon2 else 'bcrypt'} hashing",
                files=["models/user.py"],
                estimated_minutes=45,
            ),
            Task(
                id="auth-task-2",
                title="Implement JWT token generation and validation",
                description=f"Create JWT service with {'RS256' if use_rs256 else 'HS256'} signing",
                files=["auth/jwt.py"],
                dependencies=["auth-task-1"],
                estimated_minutes=60,
            ),
            Task(
                id="auth-task-3",
                title="Implement authentication endpoints",
                description="Create login, register, and token refresh endpoints",
                files=["routers/auth.py"],
                dependencies=["auth-task-2"],
                estimated_minutes=50,
            ),
            Task(
                id="auth-task-4",
                title="Implement authentication middleware",
                description="Create JWT verification middleware for protected routes",
                files=["middleware/auth.py"],
                dependencies=["auth-task-2"],
                estimated_minutes=40,
            ),
            Task(
                id="auth-task-5",
                title="Write comprehensive tests",
                description="Integration tests for full auth flow including edge cases",
                files=["tests/test_auth.py"],
                dependencies=["auth-task-3", "auth-task-4"],
                estimated_minutes=60,
            ),
        ]

        return tasks

    def _decompose_api_feature(
        self, feature_description: str, research_results: dict | None
    ) -> list[Task]:
        """Decompose API endpoint features"""

        return [
            Task(
                id="api-task-1",
                title="Design API schema",
                description="Define request/response models and validation",
                files=["schemas/api.py"],
                estimated_minutes=30,
            ),
            Task(
                id="api-task-2",
                title="Implement API endpoints",
                description="Create FastAPI route handlers",
                files=["routers/api.py"],
                dependencies=["api-task-1"],
                estimated_minutes=60,
            ),
            Task(
                id="api-task-3",
                title="Add API documentation",
                description="Write OpenAPI/Swagger docs",
                files=["docs/api.md"],
                dependencies=["api-task-2"],
                estimated_minutes=20,
            ),
            Task(
                id="api-task-4",
                title="Write API tests",
                description="Test all endpoints with various inputs",
                files=["tests/test_api.py"],
                dependencies=["api-task-2"],
                estimated_minutes=45,
            ),
        ]

    def _decompose_database_feature(
        self, feature_description: str, research_results: dict | None
    ) -> list[Task]:
        """Decompose database/model features"""

        return [
            Task(
                id="db-task-1",
                title="Design database schema",
                description="Create SQLAlchemy models",
                files=["models/database.py"],
                estimated_minutes=40,
            ),
            Task(
                id="db-task-2",
                title="Create database migrations",
                description="Generate Alembic migrations",
                files=["alembic/versions/"],
                dependencies=["db-task-1"],
                estimated_minutes=20,
            ),
            Task(
                id="db-task-3",
                title="Implement CRUD operations",
                description="Create database access layer",
                files=["crud/database.py"],
                dependencies=["db-task-1"],
                estimated_minutes=50,
            ),
            Task(
                id="db-task-4",
                title="Write database tests",
                description="Test models and CRUD operations",
                files=["tests/test_database.py"],
                dependencies=["db-task-3"],
                estimated_minutes=40,
            ),
        ]

    def _decompose_ui_feature(
        self, feature_description: str, research_results: dict | None
    ) -> list[Task]:
        """Decompose UI/frontend features"""

        return [
            Task(
                id="ui-task-1",
                title="Design component structure",
                description="Create React/Vue component hierarchy",
                files=["components/"],
                estimated_minutes=30,
            ),
            Task(
                id="ui-task-2",
                title="Implement UI components",
                description="Build reusable components",
                files=["components/*.tsx"],
                dependencies=["ui-task-1"],
                estimated_minutes=90,
            ),
            Task(
                id="ui-task-3",
                title="Add styling and responsive design",
                description="CSS/Tailwind styling",
                files=["styles/"],
                dependencies=["ui-task-2"],
                estimated_minutes=45,
            ),
            Task(
                id="ui-task-4",
                title="Write component tests",
                description="Jest/React Testing Library tests",
                files=["tests/components/"],
                dependencies=["ui-task-2"],
                estimated_minutes=40,
            ),
        ]

    def _decompose_generic_feature(
        self, feature_description: str, research_results: dict | None
    ) -> list[Task]:
        """Fallback for features that don't match patterns"""

        return [
            Task(
                id="generic-task-1",
                title="Research and design",
                description=f"Design solution for: {feature_description}",
                files=["DESIGN.md"],
                estimated_minutes=30,
            ),
            Task(
                id="generic-task-2",
                title="Core implementation",
                description="Implement main functionality",
                files=["src/main.py"],
                dependencies=["generic-task-1"],
                estimated_minutes=90,
            ),
            Task(
                id="generic-task-3",
                title="Write tests",
                description="Comprehensive test coverage",
                files=["tests/test_main.py"],
                dependencies=["generic-task-2"],
                estimated_minutes=45,
            ),
            Task(
                id="generic-task-4",
                title="Documentation",
                description="Write user documentation",
                files=["docs/feature.md"],
                dependencies=["generic-task-2"],
                estimated_minutes=20,
            ),
        ]

    async def broadcast_tasks(self, tasks: list[Task]):
        """
        Broadcast available tasks to all agents.

        Agents can claim tasks by sending messages back.

        Args:
            tasks: Tasks to broadcast
        """

        available_tasks = [t for t in tasks if t.status == "available"]

        if not available_tasks:
            return

        # Format task list
        task_list = "\n".join(
            [
                f"- {t.id}: {t.title}"
                + (f" (depends on: {', '.join(t.dependencies)})" if t.dependencies else "")
                for t in available_tasks
            ]
        )

        message_content = (
            f"Available tasks:\n{task_list}\n\n"
            f"Claim with: claudeswarm send-message work-distributor INFO 'claim:task_id'"
        )

        # Broadcast via messaging system (use run_in_executor to avoid blocking event loop)
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Use default executor
                self.messaging.broadcast_message,
                "work-distributor",
                MessageType.INFO,
                message_content,
            )
            print(f"📋 Broadcast {len(available_tasks)} available tasks")
        except Exception as e:
            print(f"⚠️  Failed to broadcast tasks: {e}")
            # Still print locally for visibility
            print(f"📋 Available tasks ({len(available_tasks)}):")
            for task in available_tasks:
                deps = f" (depends on: {', '.join(task.dependencies)})" if task.dependencies else ""
                print(f"  - {task.id}: {task.title}{deps}")

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """
        Assign a task to an agent.

        Args:
            task_id: Task to claim
            agent_id: Agent claiming the task

        Returns:
            True if successfully claimed, False if already claimed or blocked
        """

        # Use lock to prevent race conditions when multiple agents claim simultaneously
        with self._task_lock:
            if task_id not in self.tasks:
                return False

            task = self.tasks[task_id]

            # Check if already claimed
            if task.status != "available":
                return False

            # Check if dependencies are met
            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    return False
                dep_task = self.tasks[dep_id]
                if dep_task.status != "completed":
                    return False

            # Claim task (inside lock - atomic operation)
            task.agent_id = agent_id
            task.status = "claimed"
            task.claimed_at = datetime.now()

            print(f"✓ Task {task_id} claimed by {agent_id}")

        # Broadcast claim (outside lock - don't hold lock during I/O)
        try:
            self.messaging.broadcast_message(
                sender_id="work-distributor",
                msg_type=MessageType.INFO,
                content=f"{agent_id} claimed: {task.title}",
            )
        except Exception as e:
            print(f"⚠️  Failed to broadcast claim: {e}")

        return True

    def complete_task(self, task_id: str) -> bool:
        """
        Mark a task as completed.

        Args:
            task_id: Task that was completed

        Returns:
            True if successfully marked complete
        """

        # Use lock to prevent race conditions when accessing shared state
        with self._task_lock:
            if task_id not in self.tasks:
                return False

            task = self.tasks[task_id]
            task.status = "completed"
            task.completed_at = datetime.now()

            print(f"✓ Task {task_id} completed by {task.agent_id}")

            # Check if this unblocks other tasks
            unblocked = self._check_unblocked_tasks(task_id)
            if unblocked:
                print(f"  → Unblocked tasks: {', '.join(unblocked)}")

            return True

    def _check_unblocked_tasks(self, completed_task_id: str) -> list[str]:
        """
        Check which tasks are now available after a completion.

        Note: Must be called with self._task_lock held.
        """

        unblocked = []

        for task_id, task in self.tasks.items():
            if task.status != "available":
                continue

            if completed_task_id not in task.dependencies:
                continue

            # Check if all dependencies are now met
            all_deps_met = all(
                self.tasks[dep_id].status == "completed"
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )

            if all_deps_met:
                unblocked.append(task_id)

        return unblocked

    def get_progress_summary(self) -> dict:
        """
        Get overall progress summary.

        Returns:
            Dictionary with progress statistics
        """

        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")
        in_progress = sum(1 for t in self.tasks.values() if t.status in ["claimed", "in_progress"])
        available = sum(1 for t in self.tasks.values() if t.status == "available")
        blocked = sum(1 for t in self.tasks.values() if t.status == "blocked")

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "available": available,
            "blocked": blocked,
            "completion_pct": (completed / total * 100) if total > 0 else 0,
        }

    def get_agent_workload(self) -> dict[str, list[str]]:
        """
        Get which tasks each agent is working on.

        Returns:
            Dictionary mapping agent_id to list of task_ids
        """

        workload = {}

        for task_id, task in self.tasks.items():
            if task.agent_id:
                if task.agent_id not in workload:
                    workload[task.agent_id] = []
                workload[task.agent_id].append(task_id)

        return workload
