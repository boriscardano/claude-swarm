# Contributing to Claude Swarm

Thank you for your interest in contributing to Claude Swarm! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Contribute

### Reporting Bugs

1. **Check existing issues** - Search [GitHub Issues](https://github.com/boriscardano/claude-swarm/issues) to see if the bug has already been reported.
2. **Create a new issue** - If not found, open a new issue with:
   - A clear, descriptive title
   - Steps to reproduce the bug
   - Expected vs actual behavior
   - Your environment (OS, Python version, tmux version)
   - Relevant logs or error messages

### Suggesting Features

1. **Check existing issues** - Your idea may already be discussed.
2. **Open a feature request** - Describe:
   - The problem you're trying to solve
   - Your proposed solution
   - Alternative approaches you've considered

### Pull Request Process

1. **Fork the repository** and create a feature branch from `main`
2. **Make your changes** following our code style guidelines
3. **Add tests** for any new functionality
4. **Run the test suite** to ensure all tests pass
5. **Update documentation** if needed
6. **Submit a pull request** with a clear description of changes

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- tmux (for integration testing)

### Setting Up Your Environment

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/claude-swarm.git
cd claude-swarm

# Install dependencies with uv (recommended)
uv sync --all-extras

# Or with pip
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_messaging.py

# Run only unit tests (skip integration)
pytest -m "not integration"
```

### Code Quality Tools

```bash
# Format code with black
black src/ tests/

# Lint with ruff
ruff check src/ tests/

# Type checking with mypy
mypy src/

# Security scan with bandit
bandit -r src/
```

## Code Style Guidelines

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use [Black](https://black.readthedocs.io/) for formatting (line length: 100)
- Use type hints for function parameters and return values
- Write docstrings for public functions and classes

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb in imperative mood (Add, Fix, Update, Remove)
- Keep the first line under 50 characters
- Add more detail in the body if needed

Examples:
```
Add file locking timeout configuration
Fix race condition in agent discovery
Update documentation for CLI commands
```

### Testing

- Write tests for all new functionality
- Maintain or improve test coverage
- Use descriptive test names that explain what's being tested
- Include both positive and negative test cases

## Project Structure

```
claude-swarm/
├── src/claudeswarm/     # Core source code
│   ├── cli.py           # Command-line interface
│   ├── discovery.py     # Agent discovery
│   ├── messaging.py     # Inter-agent messaging
│   ├── locking.py       # File locking
│   └── ...
├── tests/               # Test suite
│   ├── integration/     # Integration tests
│   └── test_*.py        # Unit tests
├── docs/                # Documentation
└── examples/            # Example configurations
```

## Getting Help

- Read the [documentation](docs/)
- Check [existing issues](https://github.com/boriscardano/claude-swarm/issues)
- Open a new issue for questions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
