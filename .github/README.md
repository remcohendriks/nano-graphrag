# GitHub Actions Setup

## PR Review Automation

This repository uses GitHub Actions to automate code reviews using Claude CLI on a self-hosted runner.

### Triggering Reviews

To trigger a review on a pull request, comment:
```
/review round-1
```

For subsequent review rounds:
```
/review round-2
/review round-3
```

### Security

- **Authorization**: Only `remcohendriks` can trigger reviews
- **Concurrency**: Only one review can run per PR at a time
- **Duplicate Prevention**: Reviews are cached by SHA - same code won't be reviewed twice

### Requirements

1. **Self-hosted Runner**: Must have Claude CLI installed and configured
2. **Repository Permissions**: Runner needs write access to commit reviews
3. **GitHub Token**: Automatically provided by GitHub Actions

### Review Output

Reviews are saved to the `reviews/` directory with the naming pattern:
```
reviews/PR-{number}-round-{round}-{sha}.md
```

### Workflow Files

- `.github/workflows/pr-review.yml` - Main workflow definition
- `.github/review-prompts/claude-prompt.md` - Review prompt template

### Customization

To modify the review focus or criteria, edit the prompt template in `.github/review-prompts/claude-prompt.md`.

### Troubleshooting

If a review fails:
1. Check the Actions tab for error logs
2. Verify Claude CLI is properly configured on the runner
3. Ensure the runner has sufficient API credits/access
4. Check that the PR branch is up to date with the base branch

### Manual Review

If automated review is unavailable, you can run manually:
```bash
# Generate diff
git diff main..feature-branch > pr-diff.txt

# Run Claude review
cat .github/review-prompts/claude-prompt.md pr-diff.txt | claude --max-tokens 8000 > review.md
```