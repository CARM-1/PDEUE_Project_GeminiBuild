import pathlib

def get_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    return here.parents[2] if (here.parents[2] / 'deploy').exists() else pathlib.Path.cwd()

def test_terraform_manifests_presence():
    root = get_repo_root()
    tf_dir = root / 'deploy' / 'terraform'
    assert tf_dir.exists(), f'Missing Terraform directory at {tf_dir}'
    assert (tf_dir / 'main.tf').exists()
    assert (tf_dir / 'vpc.tf').exists()
    assert (tf_dir / 'secrets.tf').exists()
    assert (tf_dir / 'ecs.tf').exists()

def test_vpc_configuration_conformance():
    root = get_repo_root()
    vpc_tf = (root / 'deploy' / 'terraform' / 'vpc.tf').read_text(encoding='utf-8')
    assert '10.0.0.0/16' in vpc_tf
    assert 'pdeue-private-a' in vpc_tf
    assert 'pdeue-private-b' in vpc_tf

def test_secrets_and_ecs_conformance():
    root = get_repo_root()
    sec_tf = (root / 'deploy' / 'terraform' / 'secrets.tf').read_text(encoding='utf-8')
    assert 'pdeue/rds_url' in sec_tf
    assert 'pdeue/hmac_key' in sec_tf
    ecs_tf = (root / 'deploy' / 'terraform' / 'ecs.tf').read_text(encoding='utf-8')
    assert 'pdeue-cluster' in ecs_tf
    assert '/ecs/pdeue-production' in ecs_tf
