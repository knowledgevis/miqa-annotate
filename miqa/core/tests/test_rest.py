import json
from uuid import UUID

from guardian.shortcuts import assign_perm, get_perms
import pytest

from miqa.core.rest.frame import FrameSerializer
from miqa.core.rest.permissions import has_read_perm, has_review_perm
from miqa.core.rest.project import ProjectSerializer
from miqa.core.rest.scan import ScanSerializer
from miqa.core.rest.scan_decision import ScanDecisionSerializer
from miqa.core.rest.user import UserSerializer


# to avoid failing a comparison between a string id and UUID
class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            # if the obj is uuid, we simply return the value of uuid
            return str(obj)
        return json.JSONEncoder.default(self, obj)


@pytest.mark.django_db
def test_api_token_access(user, api_client):
    password = 'letmein'
    user.set_password(password)
    user.save()

    resp_1 = api_client.post(
        '/api-token-auth/',
        data={
            'username': user.username,
            'password': password,
        },
    )
    assert resp_1.status_code == 200
    token = resp_1.json()['token']

    resp_2 = api_client.get('/api/v1/users', HTTP_AUTHORIZATION=f'Token {token}')
    assert resp_2.status_code == 200


@pytest.mark.django_db
def test_projects_list(user_api_client, project, user):
    user_api_client = user_api_client()
    resp = user_api_client.get('/api/v1/projects')
    assert resp.status_code == 200
    if not has_read_perm(get_perms(user, project)):
        assert resp.data == {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
    else:
        assert resp.data == {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [ProjectSerializer(project).data],
        }


@pytest.mark.django_db
def test_project_status(
    project,
    experiment,
    scan_factory,
    scan_decision_factory,
    user_factory,
):
    # 3 of 5 scans marked as complete
    decisions = [
        ('U', 'tier_1_reviewer'),
        ('U', 'tier_2_reviewer'),
        ('UN', 'tier_1_reviewer'),  # needs tier 2 review
        ('UN', 'tier_2_reviewer'),
        ('Q?', 'tier_1_reviewer'),  # needs tier 2 review
    ]
    scans = [scan_factory(experiment=experiment) for i in range(len(decisions))]
    for decision, scan in zip(decisions, scans):
        decider = user_factory()
        assign_perm(decision[1], decider, project)
        scan_decision_factory(scan=scan, creator=decider, decision=decision[0])
    # project.refresh_from_db()
    status = project.get_status()
    assert status['total_scans'] == len(scans)
    assert status['total_complete'] == 3


@pytest.mark.django_db
def test_project_settings_get(user_api_client, project, user):
    resp = user_api_client().get(f'/api/v1/projects/{project.id}/settings')
    if not has_read_perm(get_perms(user, project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200
        assert all(key in resp.data for key in ['import_path', 'export_path', 'permissions'])


@pytest.mark.django_db
def test_project_settings_put(user_api_client, project_factory, user_factory, user):
    creator = user_factory()
    project = project_factory(creator=creator)
    user_api_client = user_api_client()
    my_perms = get_perms(user, project)
    new_perms = {
        'collaborator': [user.username] if 'collaborator' in my_perms else [],
        'tier_1_reviewer': [user.username] if 'tier_1_reviewer' in my_perms else [],
        'tier_2_reviewer': [user.username] if 'tier_2_reviewer' in my_perms else [],
    }
    resp = user_api_client.put(
        f'/api/v1/projects/{project.id}/settings',
        data={
            'import_path': '/new/fake/path',
            'export_path': '/new/fake/path',
            'permissions': new_perms,
        },
    )
    if not user.is_superuser:
        assert resp.status_code == 403
    else:
        expected_perms = {
            'collaborator': [UserSerializer(user).data]
            if 'collaborator' in my_perms
            and 'tier_1_reviewer' not in my_perms
            and 'tier_2_reviewer' not in my_perms
            else [],
            'tier_1_reviewer': [UserSerializer(user).data]
            if 'tier_1_reviewer' not in my_perms and 'tier_2_reviewer' not in my_perms
            else [],
            'tier_2_reviewer': [UserSerializer(user).data] if 'tier_2_reviewer' in my_perms else [],
        }
        assert resp.status_code == 200
        assert user_api_client.get(f'/api/v1/projects/{project.id}/settings').data == {
            'import_path': '/new/fake/path',
            'export_path': '/new/fake/path',
            'anatomy_orientation': 'LPS',
            'permissions': expected_perms,
            'default_email_recipients': project.default_email_recipients.split('\n'),
            'artifacts': [
                'flow_artifact',
                'full_brain_coverage',
                'ghosting_motion',
                'inhomogeneity',
                'lesions',
                'misalignment',
                'normal_variants',
                'susceptibility_metal',
                'swap_wraparound',
                'truncation_artifact',
            ],
        }
        my_new_perms = get_perms(user, project)
        if 'collaborator' in my_perms:
            assert has_read_perm(my_new_perms)
        elif 'tier_1_reviewer' in my_perms or 'tier_2_reviewer' in my_perms:
            assert has_review_perm(my_new_perms)


@pytest.mark.django_db
def test_settings_endpoint_requires_superuser(user_api_client, project_factory, user_factory, user):
    creator = user_factory()
    project = project_factory(creator=creator)
    resp = user_api_client().put(
        f'/api/v1/projects/{project.id}/settings',
        data={
            'import_path': '/new/fake/path',
            'export_path': '/new/fake/path',
            'permissions': {},
        },
    )
    if not user.is_superuser:
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200


@pytest.mark.django_db
def test_experiments_list(user_api_client, experiment, user):
    resp = user_api_client(project=experiment.project).get('/api/v1/experiments')
    assert resp.status_code == 200
    if not has_read_perm(get_perms(user, experiment.project)):
        assert resp.data == {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
    else:
        expected_result = [
            {
                'id': experiment.id,
                'name': experiment.name,
                'lock_owner': None,
                'scans': [],
                'project': experiment.project.id,
                'note': experiment.note,
            }
        ]
        assert resp.data == {
            'count': 1,
            'next': None,
            'previous': None,
            'results': expected_result,
        }


@pytest.mark.django_db
def test_experiment_retrieve(user_api_client, experiment, user):
    resp = user_api_client(project=experiment.project).get(f'/api/v1/experiments/{experiment.id}')
    if not has_read_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 404
    else:
        assert resp.status_code == 200
        # We want to assert that the nested project document is only the id
        assert resp.json() == {
            'id': experiment.id,
            'lock_owner': None,
            'name': experiment.name,
            'note': experiment.note,
            'project': experiment.project.id,
            'scans': [],
        }


@pytest.mark.django_db
def test_scans_list(user_api_client, scan, user):
    resp = user_api_client(project=scan.experiment.project).get('/api/v1/scans')
    assert resp.status_code == 200
    if not has_read_perm(get_perms(user, scan.experiment.project)):
        assert resp.data == {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
    else:
        expected_result = [ScanSerializer(scan).data]
        assert json.loads(json.dumps(resp.data, cls=UUIDEncoder)) == {
            'count': 1,
            'next': None,
            'previous': None,
            'results': expected_result,
        }


@pytest.mark.django_db
def test_scan_decisions_list(user_api_client, scan_decision, user):
    resp = user_api_client(project=scan_decision.scan.experiment.project).get(
        '/api/v1/scan-decisions'
    )
    assert resp.status_code == 200
    if not has_read_perm(get_perms(user, scan_decision.scan.experiment.project)):
        assert resp.data == {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
    else:
        expected_result = [ScanDecisionSerializer(scan_decision).data]
        assert resp.data == {
            'count': 1,
            'next': None,
            'previous': None,
            'results': expected_result,
        }


@pytest.mark.django_db
def test_frames_list(user_api_client, frame, user):
    resp = user_api_client(project=frame.scan.experiment.project).get('/api/v1/frames')
    assert resp.status_code == 200
    if not has_read_perm(get_perms(user, frame.scan.experiment.project)):
        assert resp.data == {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
    else:
        assert resp.data == {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [FrameSerializer(frame).data],
        }


@pytest.mark.django_db
def test_experiment_lock_acquire_requires_auth(api_client, experiment):
    resp = api_client.post(f'/api/v1/experiments/{experiment.id}/lock')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_experiment_lock_acquire(user_api_client, experiment, user):
    resp = user_api_client(project=experiment.project).post(
        f'/api/v1/experiments/{experiment.id}/lock'
    )
    if not has_review_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200

        experiment.refresh_from_db()
        assert experiment.lock_owner == user


@pytest.mark.django_db
def test_experiment_lock_reacquire_ok(user_api_client, experiment_factory, user):
    experiment = experiment_factory(lock_owner=user)
    resp = user_api_client(project=experiment.project).post(
        f'/api/v1/experiments/{experiment.id}/lock'
    )
    if not has_review_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200


@pytest.mark.django_db
def test_experiment_lock_denied(user_api_client, experiment_factory, user_factory, user):
    owner = user_factory()
    experiment = experiment_factory(lock_owner=owner)
    resp = user_api_client(project=experiment.project).post(
        f'/api/v1/experiments/{experiment.id}/lock'
    )
    if not has_review_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 409

        experiment.refresh_from_db()
        assert experiment.lock_owner == owner


@pytest.mark.django_db
def test_experiment_lock_release(user_api_client, experiment_factory, user):
    experiment = experiment_factory(lock_owner=user)
    resp = user_api_client(project=experiment.project).delete(
        f'/api/v1/experiments/{experiment.id}/lock'
    )
    if not has_review_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 200

        experiment.refresh_from_db()
        assert experiment.lock_owner is None


@pytest.mark.django_db
def test_experiment_lock_only_owner_can_release(
    user_api_client, experiment_factory, user_factory, user
):
    owner = user_factory()
    experiment = experiment_factory(lock_owner=owner)
    resp = user_api_client(project=experiment.project).delete(
        f'/api/v1/experiments/{experiment.id}/lock'
    )
    if not has_review_perm(get_perms(user, experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 409

        experiment.refresh_from_db()
        assert experiment.lock_owner.id == owner.id


@pytest.mark.django_db
def test_read_without_lock_ok(user_api_client, scan_decision, user):
    resp = user_api_client().get(f'/api/v1/scan-decisions/{scan_decision.id}')
    if not has_read_perm(get_perms(user, scan_decision.scan.experiment.project)):
        assert resp.status_code == 404
    else:
        assert resp.status_code == 200


@pytest.mark.django_db
def test_create_scan_decision_without_lock_fails(user_api_client, scan, user):
    resp = user_api_client().post(
        '/api/v1/scan-decisions',
        data={
            'scan': scan.id,
            'decision': 'U',
        },
    )
    if not has_review_perm(get_perms(user, scan.experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 403
        assert resp.data['detail'] == 'You must lock the experiment before performing this action.'


@pytest.mark.django_db
def test_create_scan_decision_with_lock(user_api_client, scan, user):
    scan.experiment.lock_owner = user
    scan.experiment.save(update_fields=['lock_owner'])

    resp = user_api_client().post(
        '/api/v1/scan-decisions',
        data={
            'scan': scan.id,
            'decision': 'U',
            'note': '',
        },
    )
    if not has_review_perm(get_perms(user, scan.experiment.project)):
        assert resp.status_code == 403
    else:
        assert resp.status_code == 201
        decisions = scan.decisions.all()
        assert len(decisions) == 1
        assert decisions[0].decision == 'U'
