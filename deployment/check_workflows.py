import pathlib

workflows = list(pathlib.Path('.github/workflows').glob('*.y*ml'))
assert workflows, 'No workflows found'
for path in workflows:
    text = path.read_text()
    assert 'ubuntu-latest' not in text, f'{path}: GitHub-hosted runner'
    assert 'runs-on: [self-hosted, linux, x64, isty-ci]' in text, f'{path}: missing runner labels'
    for command in ('docker system prune', 'docker volume prune', 'docker image prune'):
        assert command not in text, f'{path}: shared Docker cleanup'
    if path.name in ('deploy.yml', 'migrations.yml'):
        assert 'workflow_dispatch:' in text
        assert '\n  push:' not in text and '\n  pull_request:' not in text
print('Workflow routing and manual deployment checks passed')
