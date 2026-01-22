"""
Autonomous Development Loop

This module implements the main orchestrator for autonomous feature development
where multiple agents collaborate for hours without human intervention.

Core phases:
1. Research (Agent 0) - Research best practices and security considerations
2. Planning (All agents) - Break down feature into tasks
3. Implementation (Agents 1-3) - Parallel implementation of tasks
4. Code Review (Cross-review) - Agents review each other's work
5. Consensus (All agents) - Resolve disagreements through voting
6. Testing (Agent 0) - Run tests and validate implementation
7. Deployment (Agent 3) - Create GitHub PR with changes

Author: agent-1
Created: 2025-11-19 (E2B Hackathon Prep)
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass

from claudeswarm.messaging import MessagingSystem, MessageType
from claudeswarm.workflows.work_distributor import WorkDistributor
from claudeswarm.workflows.code_review import CodeReviewProtocol
from claudeswarm.workflows.consensus import ConsensusEngine


@dataclass
class Task:
    """Represents a single development task"""
    id: str
    title: str
    description: str
    files: List[str]
    agent_id: Optional[str] = None
    status: str = "available"  # available, claimed, in_progress, completed, blocked


@dataclass
class ReviewFeedback:
    """Code review feedback from an agent"""
    reviewer_id: str
    author_id: str
    files: List[str]
    issues: List[str]
    suggestions: List[str]
    evidence: List[str]  # Links to docs/research supporting feedback
    approved: bool


class AutonomousDevelopmentLoop:
    """
    Main orchestrator for autonomous feature development.

    This class coordinates multiple agents working together for hours
    on complex features - researching, implementing, reviewing, debating,
    and deploying code autonomously.

    Example:
        loop = AutonomousDevelopmentLoop(
            sandbox_id="abc123",
            num_agents=4,
            mcp_bridge=mcp_bridge
        )
        pr_url = await loop.develop_feature(
            "Add JWT authentication to FastAPI app",
            max_duration_hours=2
        )
    """

    # Maximum number of agents allowed to prevent resource exhaustion
    MAX_AGENTS = 100

    def __init__(
        self,
        sandbox_id: str,
        num_agents: int = 4,
        mcp_bridge=None  # MCPBridge instance
    ):
        if num_agents > self.MAX_AGENTS:
            raise ValueError(f"num_agents must not exceed {self.MAX_AGENTS}")
        if num_agents < 1:
            raise ValueError("num_agents must be at least 1")

        self.sandbox_id = sandbox_id
        self.num_agents = num_agents
        self.mcp_bridge = mcp_bridge
        self.agents = [f"agent-{i+1}" for i in range(num_agents)]

        # Initialize workflow components
        self.work_distributor = WorkDistributor(num_agents)
        self.code_review = CodeReviewProtocol(num_agents)
        self.consensus = ConsensusEngine(num_agents)
        self.messaging = MessagingSystem()

        self.tasks: List[Task] = []
        self.research_results: Optional[Dict] = None

    async def develop_feature(
        self,
        feature_description: str,
        max_duration_hours: int = 8
    ) -> str:
        """
        Main entry point for autonomous development.

        Args:
            feature_description: Natural language description of feature to build
            max_duration_hours: Maximum time to work autonomously

        Returns:
            GitHub PR URL if successful

        Raises:
            RuntimeError: If development fails or tests don't pass
        """

        print(f"🚀 Starting autonomous development: {feature_description}")
        print(f"⏱️  Max duration: {max_duration_hours} hours")
        print(f"👥 Agents: {self.num_agents}")

        start_time = datetime.now()

        try:
            # Phase 1: Research
            print("\n📚 Phase 1: Research...")
            self.research_results = await self.research_phase(feature_description)

            # Phase 2: Planning
            print("\n📋 Phase 2: Planning...")
            self.tasks = await self.planning_phase(self.research_results)

            # Phase 3: Implementation
            print("\n⚒️  Phase 3: Implementation...")
            implementations = await self.implementation_phase(self.tasks)

            # Phase 4: Code Review
            print("\n👀 Phase 4: Code Review...")
            reviews = await self.review_phase(implementations)

            # Phase 5: Consensus (if needed)
            if reviews.get('disagreements'):
                print("\n🗳️  Phase 5: Consensus...")
                await self.consensus_phase(reviews)

            # Phase 6: Testing
            print("\n🧪 Phase 6: Testing...")
            test_results = await self.testing_phase()

            # Phase 7: Deployment
            if test_results['passed']:
                print("\n🚢 Phase 7: Deployment...")
                pr_url = await self.deployment_phase()

                duration = (datetime.now() - start_time).total_seconds() / 3600
                print(f"\n✅ Feature complete! PR: {pr_url}")
                print(f"⏱️  Total time: {duration:.2f} hours")
                return pr_url
            else:
                print("\n❌ Tests failed. Starting fix iteration...")
                return await self.fix_and_retry(test_results)

        except Exception as e:
            print(f"\n❌ Error during development: {e}")
            raise

    async def research_phase(self, feature_description: str) -> Dict:
        """
        Agent 0 researches the feature using Exa and Perplexity MCPs.

        Args:
            feature_description: What to research

        Returns:
            Dictionary with research findings, best practices, security considerations
        """

        agent_id = "agent-0"
        print(f"  [{agent_id}] Researching: {feature_description}")

        # TODO: Use real MCP calls when available
        # exa_results = await self.mcp_bridge.call_mcp(
        #     "exa",
        #     "search",
        #     {
        #         "query": f"{feature_description} best practices tutorial",
        #         "num_results": 5
        #     }
        # )

        # perplexity_validation = await self.mcp_bridge.call_mcp(
        #     "perplexity",
        #     "ask",
        #     {
        #         "question": f"What are security considerations for {feature_description}?"
        #     }
        # )

        # Placeholder research results
        research_summary = {
            "feature": feature_description,
            "best_practices": [
                "Use RS256 for JWT signing in production",
                "Set token expiry to 15 minutes for access tokens",
                "Implement refresh token rotation",
                "Use argon2 for password hashing",
                "Validate all inputs"
            ],
            "security": [
                "Never log JWT tokens",
                "Use HTTPS only",
                "Implement rate limiting on auth endpoints",
                "Use secure random for token generation"
            ],
            "recommendations": [
                "Follow OWASP best practices",
                "Implement proper error handling",
                "Add comprehensive tests"
            ]
        }

        # Broadcast research complete
        try:
            recommendations_str = ", ".join(research_summary['recommendations'][:2])
            self.messaging.broadcast_message(
                sender_id=agent_id,
                msg_type=MessageType.INFO,
                content=f"Research complete. Key recommendations: {recommendations_str}"
            )
        except Exception as e:
            print(f"⚠️  Failed to broadcast research completion: {e}")

        print(f"  [{agent_id}] Research complete. Found {len(research_summary['best_practices'])} best practices")

        return research_summary

    async def planning_phase(self, research_results: Dict) -> List[Task]:
        """
        Break down feature into specific tasks based on research.

        Args:
            research_results: Output from research phase

        Returns:
            List of tasks for agents to claim
        """

        print(f"  [coordinator] Breaking down feature into tasks...")

        # TODO: Use AI to intelligently decompose feature
        # For now, use heuristic based on common patterns

        feature = research_results["feature"].lower()

        # Smart task decomposition based on feature type
        if "auth" in feature or "jwt" in feature:
            tasks = [
                Task(
                    id="task-1",
                    title="Implement user model with password hashing",
                    description="Create User model, use argon2 for hashing as per research",
                    files=["models/user.py"]
                ),
                Task(
                    id="task-2",
                    title="Implement JWT token generation and validation",
                    description="Create JWT service with RS256 signing, 15min expiry",
                    files=["auth/jwt.py"]
                ),
                Task(
                    id="task-3",
                    title="Implement authentication endpoints",
                    description="Create login, register, refresh token endpoints",
                    files=["routers/auth.py"]
                ),
                Task(
                    id="task-4",
                    title="Implement auth middleware",
                    description="JWT verification middleware for protected routes",
                    files=["middleware/auth.py"]
                ),
                Task(
                    id="task-5",
                    title="Write integration tests",
                    description="Test full auth flow including edge cases",
                    files=["tests/test_auth.py"]
                )
            ]
        else:
            # Generic task breakdown
            tasks = [
                Task(
                    id="task-1",
                    title="Research and design",
                    description=f"Design solution for: {research_results['feature']}",
                    files=["DESIGN.md"]
                ),
                Task(
                    id="task-2",
                    title="Core implementation",
                    description="Implement core functionality",
                    files=["src/main.py"]
                ),
                Task(
                    id="task-3",
                    title="Write tests",
                    description="Comprehensive test coverage",
                    files=["tests/test_main.py"]
                )
            ]

        # Broadcast available tasks via WorkDistributor
        await self.work_distributor.broadcast_tasks(tasks)

        print(f"  [coordinator] Created {len(tasks)} tasks")
        for task in tasks:
            print(f"    - {task.title}")

        return tasks

    async def implementation_phase(self, tasks: List[Task]) -> List[Dict]:
        """
        Agents claim and implement tasks in parallel.

        Args:
            tasks: List of tasks to implement

        Returns:
            List of implementations with status
        """

        print(f"  [system] Agents claiming tasks...")

        # Simulate agents claiming tasks
        # In real implementation, agents would message to claim
        implementations = []

        for i, task in enumerate(tasks[:self.num_agents-1]):  # Leave one agent for testing
            agent_id = f"agent-{i+1}"
            task.agent_id = agent_id
            task.status = "in_progress"

            print(f"  [{agent_id}] Claimed: {task.title}")

            # TODO: Agent would acquire file locks
            # for file_path in task.files:
            #     self.lock_manager.acquire_lock(
            #         file_path=file_path,
            #         agent_id=agent_id,
            #         reason=f"Implementing {task.title}"
            #     )

            # Simulate implementation time
            await asyncio.sleep(0.5)

            task.status = "completed"
            print(f"  [{agent_id}] Completed: {task.title}")

            # Broadcast completion
            try:
                self.messaging.broadcast_message(
                    sender_id=agent_id,
                    msg_type=MessageType.COMPLETED,
                    content=f"Completed {task.title}"
                )
            except Exception as e:
                print(f"⚠️  Failed to broadcast completion: {e}")

            implementations.append({
                "task": task,
                "agent": agent_id,
                "status": "completed"
            })

        return implementations

    async def review_phase(self, implementations: List[Dict]) -> Dict:
        """
        Agents cross-review each other's work.

        Args:
            implementations: List of completed implementations

        Returns:
            Dictionary with reviews and any disagreements
        """

        print(f"  [system] Starting code reviews...")

        reviews = {
            "reviews": [],
            "disagreements": []
        }

        # Each agent reviews another's work (round-robin)
        for i, impl in enumerate(implementations):
            reviewer_id = f"agent-{(i+2) % self.num_agents}"
            author_id = impl['agent']

            if reviewer_id == author_id:
                continue  # Skip self-review

            print(f"  [{reviewer_id}] Reviewing {author_id}'s work on {impl['task'].title}")

            # Send review request via CodeReviewProtocol
            await self.code_review.request_review(
                author_agent=author_id,
                reviewer_agent=reviewer_id,
                files=impl['task'].files,
                task_description=impl['task'].description
            )

            # Simulate review (in real implementation, AI would review code)
            review_feedback = ReviewFeedback(
                reviewer=reviewer_id,
                author=author_id,
                files=impl['task'].files,
                issues=[],
                suggestions=["Consider adding error handling"],
                evidence=["https://docs.python.org/3/tutorial/errors.html"],
                approved=True
            )

            reviews["reviews"].append(review_feedback)

            # Simulate occasional disagreement for demo
            if i == 0:
                disagreement = {
                    "topic": "Password hashing algorithm",
                    "agent_a": author_id,
                    "position_a": "Use bcrypt (widely supported)",
                    "agent_b": reviewer_id,
                    "position_b": "Use argon2 (research recommends)",
                    "evidence_b": ["Research phase recommended argon2"]
                }
                reviews["disagreements"].append(disagreement)
                print(f"    ⚠️  Disagreement: {disagreement['topic']}")

        return reviews

    async def consensus_phase(self, reviews: Dict):
        """
        Resolve disagreements through evidence-based voting.

        Args:
            reviews: Reviews with disagreements to resolve
        """

        print(f"  [system] Resolving {len(reviews['disagreements'])} disagreements...")

        for disagreement in reviews["disagreements"]:
            topic = disagreement['topic']

            print(f"    📊 Voting on: {topic}")
            print(f"       Option A ({disagreement['agent_a']}): {disagreement['position_a']}")
            print(f"       Option B ({disagreement['agent_b']}): {disagreement['position_b']}")

            # TODO: Implement real voting mechanism
            # self.messaging.broadcast_message(
            #     sender_id="coordinator",
            #     message_type=MessageType.QUESTION,
            #     content=f"Vote: {topic}\nA: {position_a}\nB: {position_b}"
            # )

            # Simulate voting (in real implementation, collect agent votes)
            votes = {
                "option_a": 1,
                "option_b": 3  # Majority agrees with research
            }

            winner = "B" if votes["option_b"] > votes["option_a"] else "A"
            print(f"       ✅ Consensus reached: Option {winner} (votes: {votes})")

            # Broadcast decision
            try:
                self.messaging.broadcast_message(
                    sender_id="coordinator",
                    msg_type=MessageType.INFO,
                    content=f"Consensus on {topic}: Option {winner} (votes: {votes})"
                )
            except Exception as e:
                print(f"⚠️  Failed to broadcast consensus decision: {e}")

    async def testing_phase(self) -> Dict:
        """
        Run tests and validate implementation.

        Returns:
            Test results with pass/fail status
        """

        agent_id = "agent-0"
        print(f"  [{agent_id}] Running test suite...")

        # TODO: Execute real tests in E2B sandbox
        # result = await sandbox.execute_command("pytest tests/")

        # Simulate test results
        test_results = {
            "passed": True,
            "total_tests": 12,
            "passed_tests": 12,
            "failed_tests": 0,
            "failures": []
        }

        print(f"  [{agent_id}] Tests: {test_results['passed_tests']}/{test_results['total_tests']} passed")

        # Broadcast test results
        try:
            self.messaging.broadcast_message(
                sender_id=agent_id,
                msg_type=MessageType.INFO,
                content=f"Tests: {test_results['passed_tests']}/{test_results['total_tests']} passed"
            )
        except Exception as e:
            print(f"⚠️  Failed to broadcast test results: {e}")

        return test_results

    async def deployment_phase(self) -> str:
        """
        Create GitHub PR with all changes.

        Returns:
            GitHub PR URL
        """

        agent_id = "agent-3"
        print(f"  [{agent_id}] Creating GitHub pull request...")

        # TODO: Use real GitHub MCP
        # pr_result = await self.mcp_bridge.call_mcp(
        #     "github",
        #     "create_pull_request",
        #     {
        #         "title": "Add JWT authentication",
        #         "body": "Autonomous development by Claude Swarm\n\nImplemented by: agents 1-4",
        #         "branch": "feature/jwt-auth",
        #         "base": "main"
        #     }
        # )
        # pr_url = pr_result.get("url")

        # Placeholder PR URL
        pr_url = "https://github.com/demo/fastapi-starter/pull/1"

        print(f"  [{agent_id}] PR created: {pr_url}")

        # Broadcast completion
        try:
            self.messaging.broadcast_message(
                sender_id=agent_id,
                msg_type=MessageType.COMPLETED,
                content=f"PR created: {pr_url}"
            )
        except Exception as e:
            print(f"⚠️  Failed to broadcast PR creation: {e}")

        return pr_url

    async def fix_and_retry(self, test_results: Dict) -> str:
        """
        Fix test failures and retry.

        Args:
            test_results: Failed test results

        Returns:
            PR URL after fixes
        """

        print(f"  [system] Fixing {len(test_results['failures'])} test failures...")

        # TODO: Implement fix iteration
        # For now, raise error
        raise RuntimeError(f"Tests failed: {test_results['failures']}")


# Agent prompt templates for autonomous execution
AGENT_PROMPTS = {
    "research": """
    You are Agent 0 (Researcher). Your task:
    1. Use Exa MCP to research: {feature_description}
    2. Find best practices, security considerations, examples
    3. Use Perplexity MCP to validate findings
    4. Write research summary in RESEARCH.md
    5. Broadcast findings to team using claudeswarm broadcast-message
    """,

    "implement": """
    You are Agent {id} (Developer). Your task:
    1. Read RESEARCH.md for context
    2. Check available tasks: claudeswarm check-messages
    3. Claim a task by sending message
    4. Acquire file lock: claudeswarm acquire-file-lock <file> "implementing {task}"
    5. Implement your task following best practices from research
    6. Write unit tests for your code
    7. Release lock: claudeswarm release-file-lock <file>
    8. Broadcast completion: claudeswarm broadcast-message COMPLETED "Finished {task}"
    """,

    "review": """
    You are Agent {id} (Reviewer). Your task:
    1. Wait for REVIEW_REQUEST messages
    2. Read code changes from Agent {author_id}
    3. Check for: bugs, security issues, performance problems
    4. Compare against research findings from RESEARCH.md
    5. If you disagree with an approach, challenge it with evidence
    6. Send review: claudeswarm send-message {author_id} REVIEW_REQUEST "feedback"
    """,

    "test": """
    You are Agent 0 (QA). Your task:
    1. Review all implemented code
    2. Write integration tests
    3. Run full test suite: pytest tests/
    4. Report failures to team: claudeswarm broadcast-message BLOCKED "Test failures: ..."
    5. Verify fixes when agents respond
    """
}
