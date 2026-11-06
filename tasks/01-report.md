# Task 01 report
Status: DONE
Model / reasoning: claude-sonnet-5-5 / low
## What changed
- plugin.yaml: manifest; requires_hermes set to >=0.23.0 (from `hermes --version`: v0.23.0+209...)
- pyproject.toml, LICENSE, README.md, .gitignore: as specified
- __init__.py: Hermes glue (register)
- zotcore/__init__.py, settings.py, jsonout.py, tools.py, cli.py: scaffold logic
- tests/conftest.py, tests/test_01_*.py: copied verbatim from the task
## Test output
```
.......................                                                  [100%]
23 passed in 0.03s
```
## Checksums
```
2f3c8090988e03d2ddc00ce0dcf6a255654688b1f5ed8d8b88ed861dbde30f23  tests/conftest.py
f073b1a55bcd9c7828b5911686c522241ad5cdb116e1982d7d372c9e8a2349f0  tests/test_01_manifest.py
6607ff97a3bbf1d03dafaa657610ca28efd92e6ecf1cd3b7fd83a5be62024f24  tests/test_01_register.py
00bd02767cea6f6d573d07b88d680d45f54ec30e82360d9db0cf2a708f63b6de  tests/test_01_settings.py
7eae6e382bc128cead30a07912c39963d5248707502564f5e8853a2877e29bfc  tests/test_01_tools.py
```
All five match the table in the task.
## Deviations from the task
- Resolved in task 01b: root __init__.py now guarded with "if __package__:"; 23 passed on pytest 9.2.0.
## Open questions
- none
