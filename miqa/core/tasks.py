from datetime import datetime
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
from typing import Dict, List, Optional

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from celery import shared_task
import dateparser
from django.conf import settings
from django.contrib.auth.models import User
import pandas
from rest_framework.exceptions import APIException

from miqa.core.conversion.import_export_csvs import (
    import_dataframe_to_dict,
    import_dict_to_dataframe,
    validate_import_dict,
)
from miqa.core.conversion.nifti_to_zarr_ngff import nifti_to_zarr_ngff
from miqa.core.models import (
    Evaluation,
    Experiment,
    Frame,
    GlobalSettings,
    Project,
    Scan,
    ScanDecision,
)
from miqa.core.models.frame import StorageMode
from miqa.core.models.scan_decision import DECISION_CHOICES
from miqa.learning.evaluation_models import NNModel


def _get_s3_client(public: bool):
    if public:
        return boto3.client('s3', config=Config(signature_version=UNSIGNED))
    else:
        return boto3.client('s3')


def _download_from_s3(path: str, public: bool) -> bytes:
    bucket, key = path.strip()[5:].split('/', maxsplit=1)
    client = _get_s3_client(public)
    buf = BytesIO()
    client.download_fileobj(bucket, key, buf)
    return buf.getvalue()


@shared_task
def reset_demo():
    demo_project = Project.objects.get(name='Demo Project')
    demo_project.import_path = 's3://miqa-storage/miqa.csv'
    demo_project.export_path = 'samples/demo.json'
    demo_project.save()
    import_data(demo_project.id)
    Project.objects.exclude(id=demo_project.id).delete()


@shared_task
def evaluate_frame_content(frame_id):
    from miqa.learning.nn_inference import evaluate1

    frame = Frame.objects.get(id=frame_id)
    # Get the model that matches the frame's file type
    eval_model_name = frame.scan.experiment.project.model_source_type_mappings[frame.scan.scan_type]
    # Get the PyTorch model file name
    eval_model_file = frame.scan.experiment.project.model_mappings[eval_model_name]
    # Get the Predictions associated with the model
    eval_model_predictions = [
        prediction_mapping
        for prediction_mapping in frame.scan.experiment.project.model_predictions[eval_model_name]
    ]
    eval_model_nn = NNModel(eval_model_file, eval_model_predictions)

    s3_public = frame.scan.experiment.project.s3_public
    eval_model = eval_model_nn.load()
    with tempfile.TemporaryDirectory() as tmpdirname:
        # need to send a local version to NN
        if frame.storage_mode == StorageMode.LOCAL_PATH:
            dest = Path(frame.raw_path)
        else:
            dest = Path(tmpdirname, frame.content.name.split('/')[-1])
            with open(dest, 'wb') as fd:
                if frame.storage_mode == StorageMode.S3_PATH:
                    fd.write(_download_from_s3(frame.content.url, s3_public))
                else:
                    fd.write(frame.content.open().read())
        result = evaluate1(eval_model, dest)

        Evaluation.objects.create(
            frame=frame,
            evaluation_model=eval_model_name,
            results=result,
        )


@shared_task
def evaluate_data(frames_by_project):
    from miqa.learning.nn_inference import evaluate_many

    model_to_frames_map = {}
    for project_id, frame_ids in frames_by_project.items():
        project = Project.objects.get(id=project_id)
        for frame_id in frame_ids:
            frame = Frame.objects.get(id=frame_id)
            file_path = frame.raw_path
            if frame.storage_mode == StorageMode.S3_PATH or Path(file_path).exists():
                # Get the model that matches the frame's file type
                eval_model_name = project.model_source_type_mappings[frame.scan.scan_type]
                if eval_model_name not in model_to_frames_map:
                    model_to_frames_map[eval_model_name] = []
                model_to_frames_map[eval_model_name].append(frame)

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdir = Path(tmpdirname)
        for model_name, frame_set in model_to_frames_map.items():
            # Get the PyTorch model file name
            eval_model_file = project.model_mappings[model_name]
            # Get the predictions associated with the model
            eval_model_predictions = [
                prediction_mapping for prediction_mapping in project.model_predictions[model_name]
            ]
            # Load the appropriate NNModel
            eval_model_nn = NNModel(eval_model_file, eval_model_predictions)
            current_model = eval_model_nn.load()
            file_paths = {frame: frame.raw_path for frame in frame_set}
            for frame, file_path in file_paths.items():
                if frame.storage_mode == StorageMode.S3_PATH:
                    s3_public = frame.scan.experiment.project.s3_public
                    dest = tmpdir / frame.path.name
                    with open(dest, 'wb') as fd:
                        fd.write(_download_from_s3(file_path, s3_public))
                    file_paths[frame] = dest
            results = evaluate_many(current_model, list(file_paths.values()))

            Evaluation.objects.bulk_create(
                [
                    Evaluation(
                        frame=frame,
                        evaluation_model=model_name,
                        results=results[file_paths[frame]],
                    )
                    for frame in frame_set
                ]
            )


def import_data(project_id: Optional[str]):
    # Global vs Project Import
    if project_id is None:
        project = None
        import_path = GlobalSettings.load().import_path
        s3_public = False  # TODO we don't support this for global imports yet
    else:
        project = Project.objects.get(id=project_id)
        import_path = project.import_path
        s3_public = project.s3_public

    # Import CSV or JSON Files from Server / S3
    try:
        if import_path.endswith('.csv'):
            if import_path.startswith('s3://'):
                buf = _download_from_s3(import_path, s3_public).decode('utf-8')
            else:
                with open(import_path) as fd:
                    buf = fd.read()
            import_dict = import_dataframe_to_dict(
                pandas.read_csv(StringIO(buf), index_col=False, na_filter=False).astype(str),
                project,
            )
        elif import_path.endswith('.json'):
            if import_path.startswith('s3://'):
                import_dict = json.loads(_download_from_s3(import_path, s3_public))
            else:
                with open(import_path) as fd:
                    import_dict = json.load(fd)
        else:
            raise APIException(f'Invalid import file {import_path}. Must be CSV or JSON.')
    except (FileNotFoundError, boto3.exceptions.Boto3Error):
        raise APIException(f'Could not locate import file at {import_path}.')
    except PermissionError:
        raise APIException(f'MIQA lacks permission to read {import_path}.')

    import_dict, not_found_errors = validate_import_dict(import_dict, project)
    perform_import(import_dict)
    return not_found_errors


@shared_task
def perform_import(import_dict):
    new_projects: List[Project] = []
    new_experiments: List[Experiment] = []
    new_scans: List[Scan] = []
    new_frames: List[Frame] = []
    new_scan_decisions: List[ScanDecision] = []

    for project_name, project_data in import_dict['projects'].items():
        # Check if project exists
        try:
            project_object = Project.objects.get(name=project_name)
        except Project.DoesNotExist:
            raise APIException(f'Project {project_name} does not exist.')

        # Delete old imports of these projects
        Experiment.objects.filter(
            project=project_object
        ).delete()  # cascades to scans -> frames, scan_notes

        # Create Experiments
        for experiment_name, experiment_data in project_data['experiments'].items():
            notes = experiment_data.get('notes', '')
            experiment_object = Experiment(
                name=experiment_name,
                project=project_object,
                note=notes,
            )
            new_experiments.append(experiment_object)

            # Create Scans
            for scan_name, scan_data in experiment_data['scans'].items():
                subject_id = scan_data.get('subject_id', None)
                session_id = scan_data.get('session_id', None)
                scan_link = scan_data.get('scan_link', None)
                scan_object = Scan(
                    name=scan_name,
                    scan_type=scan_data['type'],
                    experiment=experiment_object,
                    subject_id=subject_id,
                    session_id=session_id,
                    scan_link=scan_link,
                )
                # Create ScanDecisions for Scans
                if 'last_decision' in scan_data and scan_data['last_decision']:
                    scan_data['decisions'] = [scan_data['last_decision']]
                for decision_data in scan_data.get('decisions', []):
                    try:
                        creator = User.objects.get(email=decision_data.get('creator', ''))
                    except User.DoesNotExist:
                        creator = None
                    note = ''
                    created = (
                        datetime.now().strftime('%Y-%m-%d %H:%M')
                        if settings.REPLACE_NULL_CREATION_DATETIMES
                        else None
                    )
                    location = {}
                    note = decision_data.get('note', '')
                    if decision_data['created']:
                        valid_dt = dateparser.parse(decision_data['created'])
                        if valid_dt:
                            created = valid_dt.strftime('%Y-%m-%d %H:%M')
                    if decision_data['location'] and decision_data['location'] != '':
                        slices = [
                            axis.split('=')[1] for axis in decision_data['location'].split(';')
                        ]
                        location = {
                            'i': slices[0],
                            'j': slices[1],
                            'k': slices[2],
                        }
                    if decision_data['decision'] in [dec[0] for dec in DECISION_CHOICES]:
                        decision = ScanDecision(
                            decision=decision_data['decision'],
                            creator=creator,
                            created=created,
                            note=note or '',
                            user_identified_artifacts={
                                artifact_name: (
                                    1
                                    if decision_data['user_identified_artifacts']
                                    and artifact_name in decision_data['user_identified_artifacts']
                                    else 0
                                )
                                for artifact_name in project_object.artifacts
                            },
                            location=location,
                            scan=scan_object,
                        )
                        new_scan_decisions.append(decision)
                new_scans.append(scan_object)
                # Create Frames
                for frame_number, frame_data in scan_data['frames'].items():
                    if frame_data['file_location']:
                        frame_object = Frame(
                            frame_number=frame_number,
                            raw_path=frame_data['file_location'],
                            scan=scan_object,
                        )
                        new_frames.append(frame_object)
                        if settings.ZARR_SUPPORT and Path(frame_object.raw_path).exists():
                            nifti_to_zarr_ngff.delay(frame_data['file_location'])

    # If any scan has no frames, it should not be created
    new_scans = [
        new_scan
        for new_scan in new_scans
        if any(new_frame.scan == new_scan for new_frame in new_frames)
    ]
    # If any experiment has no scans, it should not be created
    new_experiments = [
        new_experiment
        for new_experiment in new_experiments
        if any(new_scan.experiment == new_experiment for new_scan in new_scans)
    ]

    # Bulk create Project and it's children
    Project.objects.bulk_create(new_projects)
    Experiment.objects.bulk_create(new_experiments)
    Scan.objects.bulk_create(new_scans)
    Frame.objects.bulk_create(new_frames)
    ScanDecision.objects.bulk_create(new_scan_decisions)

    # Must use str, not UUID, to get sent to celery task properly
    frames_by_project: Dict[str, List[str]] = {}
    for frame in new_frames:
        project_id = str(frame.scan.experiment.project.id)
        if project_id not in frames_by_project:
            frames_by_project[project_id] = []
        frames_by_project[project_id].append(str(frame.id))
    evaluate_data.delay(frames_by_project)


def export_data(project_id: Optional[str]):
    if not project_id:
        export_path = GlobalSettings.load().export_path
    else:
        project = Project.objects.get(id=project_id)
        export_path = project.export_path
    parent_location = Path(export_path).parent
    if not parent_location.exists():
        raise APIException(f'No such location {parent_location} to create export file.')

    return perform_export(project_id)


@shared_task
def perform_export(project_id: Optional[str]):
    data = {'projects': {}}
    export_warnings = []

    if project_id is None:
        # A global export should export all projects
        project = None
        projects = list(Project.objects.all())
        export_path = GlobalSettings.load().export_path
    else:
        # A normal export should only export the current project
        project = Project.objects.get(id=project_id)
        projects = [project]
        export_path = project.export_path

    for project_object in projects:
        project_data = {'experiments': {}}
        for experiment_object in project_object.experiments.all():
            experiment_data = {'scans': {}, 'notes': experiment_object.note}
            for scan_object in experiment_object.scans.all():
                scan_data = {
                    'frames': {},
                    'decisions': [],
                    'type': scan_object.scan_type,
                    'subject_id': scan_object.subject_id,
                    'session_id': scan_object.session_id,
                    'scan_link': scan_object.scan_link,
                }
                for frame_object in scan_object.frames.all():
                    scan_data['frames'][frame_object.frame_number] = {
                        'file_location': frame_object.raw_path
                    }
                for decision_object in scan_object.decisions.all():
                    location = None
                    if decision_object.location:
                        location = (
                            f'i={decision_object.location["i"]};'
                            f'j={decision_object.location["j"]};'
                            f'k={decision_object.location["k"]}'
                        )
                    artifacts = ';'.join(
                        [
                            artifact
                            for artifact, value in decision_object.user_identified_artifacts.items()
                            if value == 1
                        ]
                    )
                    scan_data['decisions'].append(
                        {
                            'decision': decision_object.decision,
                            'creator': decision_object.creator.username
                            if decision_object.creator
                            else None,
                            'note': decision_object.note,
                            'created': datetime.strftime(
                                decision_object.created, '%Y-%m-%d %H:%M:%S'
                            )
                            if decision_object.created
                            else None,
                            'user_identified_artifacts': artifacts if len(artifacts) > 0 else None,
                            'location': location,
                        }
                    )
                experiment_data['scans'][scan_object.name] = scan_data
            project_data['experiments'][experiment_object.name] = experiment_data
        data['projects'][project_object.name] = project_data
    data, export_warnings = validate_import_dict(data, project)

    try:
        if export_path.endswith('csv'):
            export_df = import_dict_to_dataframe(data)
            export_df.to_csv(export_path, index=False)
        elif export_path.endswith('json'):
            with open(export_path, 'w') as fd:
                json.dump(data, fd)
        else:
            raise APIException(
                f'Unknown format for export path {export_path}. Expected csv or json.'
            )
    except PermissionError:
        raise APIException(f'MIQA lacks permission to write to {export_path}.')
    return export_warnings
