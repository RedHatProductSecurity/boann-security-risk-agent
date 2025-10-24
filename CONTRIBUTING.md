# Contributing to Boann Security Risk Agent
Contribution to the project is always welcome. We want to make contributing to this project as easy and transparent as possible.

## Set up your development environment with uv

We use [uv](https://github.com/astral-sh/uv) to manage Python dependencies and virtual environments.
You can install `uv` by following this [guide](https://docs.astral.sh/uv/getting-started/installation/).


## Pre-commit Hooks

We use [pre-commit](https://pre-commit.com/) and ruff to run linting and formatting checks on your code. You can install the pre-commit hooks by running:

```bash
pre-commit install
```

This will automatically check the code when you commit.

Alternatively, if you want to check if your changes are ready before committing, you can run the checks manually by running:

```bash
pre-commit run --all-files -v
```

```{caution}
Before pushing your changes, make sure that the pre-commit hooks have passed successfully.
```

## Filing an issue

We consider filing an issue as a great contribution. Please do not hesitate to file an issue for any bugs or improvements. Please ensure your description is
clear and has sufficient instructions to be able to reproduce the issue.


## Opening a Pull Request

If you would like to make a contribution to the source code, you can do so by creating pull requests. All pull requests will be reviewed before being merged.

To create a pull request, please follow:

1. Fork/sync the project
2. Create a new branch
3. Make and test changes
4. Make sure your code passes the `pre-commit` checks.
5. [Commit with signature](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) and push to your repository
6. [Create a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request)

Please keep pull requests small and focused. If you have a large set of changes, consider splitting them into logically grouped, smaller PRs to facilitate review and testing.

### License
By contributing to Boann Security Risk Agent, you agree that your contributions will be licensed
under the LICENSE file in the root directory of this source tree.

