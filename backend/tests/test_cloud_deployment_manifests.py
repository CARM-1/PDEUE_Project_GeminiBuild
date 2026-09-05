import json
import pathlib

def get_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    return here.parents[2] if (here.parents[2] / 'deploy').exists() else pathlib.Path.cwd()

def test_ecs_task_definition_conformance():
    root = get_repo_root()
    task_def_path = root / 'deploy' / 'ecs' / 'task-definition.json'
    assert task_def_path.exists(), f'Missing ECS task definition at {task_def_path}'
    
    manifest = json.loads(task_def_path.read_text(encoding='utf-8'))
    assert manifest['family'] == 'pdeue-engine-prod'
    assert manifest['networkMode'] == 'awsvpc'
    assert 'FARGATE' in manifest['requiresCompatibilities']
    assert int(manifest['cpu']) >= 256
    assert int(manifest['memory']) >= 512

    containers = manifest.get('containerDefinitions', [])
    assert len(containers) == 1
    core = containers[0]
    assert core['name'] == 'pdeue-core-engine'
    assert core['portMappings'][0]['containerPort'] == 8000
    assert core['healthCheck']['command'][1] == 'curl -f http://localhost:8000/healthz || exit 1'
    
    assert len(core['secrets']) >= 2
    for sec in core['secrets']:
        assert 'valueFrom' in sec
        assert sec['valueFrom'].startswith('arn:aws:secretsmanager:')
