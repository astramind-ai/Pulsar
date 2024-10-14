---
name: Bug report
about: Create a report to help us improve
title: "[BUG\U0001F41B]"
labels: ''
assignees: ''

---

## Bug Description
[Provide a clear and concise description of the bug]

## Steps to Reproduce
**Important:** Before reproducing the bug, follow these steps:
1. Locate the installation folder (usually in your home directory)
2. Open the configuration file (typically named `config.yml` or similar)
3. Change the logging level to DEBUG
4. Restart the server

Then, reproduce the bug by following these steps:
1. [First step]
2. [Second step]
3. [And so on...]

## Expected Behavior
[Describe what you expected to happen]

## Actual Behavior
[Describe what actually happened]

## Error Logs
```
[Paste relevant error logs here, ensuring the logging level is set to DEBUG]
```

## Environment
Please run the following commands and include the output:

```bash
# OS Information
uname -a

# Python version
python --version

# Installed Python packages
pip list

# GPU Information (if applicable)
nvidia-smi

# CUDA version (if applicable)
nvcc --version

# Available system resources
free -h
df -h
```

## Configuration
Provide relevant details from the server configuration file:
```yaml
[Paste relevant parts of the configuration here]
```

## Screenshots
[If applicable, add screenshots to help explain your problem]

## Possible Solutions
[If you have ideas on how to solve the issue, include them here]

## Additional Information
[Any other information you think might be helpful for diagnosing the issue]
