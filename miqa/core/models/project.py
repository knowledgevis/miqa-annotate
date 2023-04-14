import logging
from uuid import uuid4

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.dispatch import receiver
from django_extensions.db.models import TimeStampedModel
from guardian.shortcuts import assign_perm, get_perms, get_users_with_perms, remove_perm

from miqa.core.models.scan import SCAN_TYPES, Scan
from miqa.core.models.scan_decision import ArtifactState, ScanDecision
from miqa.core.models.setting import Setting


def default_evaluation_model_mapping():
    # NEXT:
    # model_mapping = Setting.objects.filter(group__key__exact='Default Evaluation Model Mapping')
    # return model_mapping
    return {
        'T1': 'MIQAMix-0',
        'T2': 'MIQAMix-0',
        'FMRI': 'MIQAT1-0',
        'MRA': 'MIQAT1-0',
        'PD': 'MIQAMix-0',
        'DTI': 'MIQAT1-0',
        'DWI': 'MIQAT1-0',
        'ncanda-t1spgr-v1': 'MIQAMix-0',
        'ncanda-mprage-v1': 'MIQAMix-0',
        'ncanda-t2fse-v1': 'MIQAMix-0',
        'ncanda-dti6b500pepolar-v1': 'MIQAMix-0',
        'ncanda-dti30b400-v1': 'MIQAT1-0',
        'ncanda-dti60b1000-v1': 'MIQAT1-0',
        'ncanda-grefieldmap-v1': 'MIQAMix-0',
        'ncanda-rsfmri-v1': 'MIQAT1-0',
    }


class AnatomyOrientation(models.TextChoices):
    LPS = 'LPS'
    RAS = 'RAS'


class Project(TimeStampedModel, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    archived = models.BooleanField(default=False)
    import_path = models.CharField(max_length=500, blank=True)
    export_path = models.CharField(max_length=500, blank=True)
    anatomy_orientation = models.CharField(
        choices=AnatomyOrientation.choices,
        default=AnatomyOrientation.LPS,
        max_length=3,
    )
    s3_public = models.BooleanField(
        default=False, help_text='Whether the S3 bucket is publicly readable.'
    )
    evaluation_models = models.JSONField(default=default_evaluation_model_mapping)
    default_email_recipients = models.TextField(blank=True)
    artifacts_group = models.ForeignKey(
        'Setting',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='artifacts_group',
        limit_choices_to={'type': 'GAT'},
    )
    files_to_models_group = models.ForeignKey(
        'Setting',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='files_to_models_group',
        limit_choices_to={'type': 'GEFMMT'},
    )
    models_group = models.ForeignKey(
        'Setting',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='models_group',
        limit_choices_to={'type': 'GEMT'},
    )
    predictions_group = models.ForeignKey(
        'Setting',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='predictions_group',
        limit_choices_to={'type': 'GEMPT'},
    )

    @property
    def artifacts(self) -> dict:
        """Gets the list of artifacts associated with the project."""
        if self.artifacts_group:
            artifacts = Setting.objects.filter(group__id=self.artifacts_group_id)

            return {artifact_name.key: ArtifactState.UNDEFINED.value for artifact_name in artifacts}
        else:
            return {}

    @property
    def model_source_type_mappings(self) -> dict:
        """Gets the list of file type to model mappings associated with the project."""
        if self.files_to_models_group:
            model_source_type_mappings = Setting.objects.filter(
                group__id=self.files_to_models_group_id
            )
            this_model_source_type_mapping = {
                model_source_type_mapping.key: model_source_type_mapping.value
                for model_source_type_mapping in model_source_type_mappings
            }
            return this_model_source_type_mapping
        else:
            return {}

    @property
    def model_mappings(self) -> dict:
        """Gets the list of models associated with the project."""
        if self.models_group:
            model_mappings = Setting.objects.filter(group__id=self.models_group_id)
            this_model_mapping = {
                model_mapping.key: model_mapping.value for model_mapping in model_mappings
            }
            return this_model_mapping
        else:
            return {}

    @property
    def model_predictions(self) -> dict:
        """Gets the list of predictions associated with the project."""
        if self.predictions_group:
            logging.debug(f'self.model_predictions_group: {self.predictions_group_id}')
            prediction_mappings = Setting.objects.filter(group__id=self.predictions_group_id)
            logging.debug(f"project's prediction_mappings: {prediction_mappings}")
            this_prediction_mapping = {}
            for prediction in prediction_mappings:
                this_prediction_mapping.setdefault(prediction.key, []).append(prediction.value)
            logging.debug(f'predictions from project: {this_prediction_mapping}')
            return this_prediction_mapping
        else:
            return {}

    def __str__(self):
        return self.name

    def clean(self):
        if not isinstance(self.evaluation_models, dict):
            raise ValidationError('Specify evaluation models as a dictionary.')
        scan_types = [x[0] for x in SCAN_TYPES]
        if any(key not in scan_types for key in self.evaluation_models.keys()):
            raise ValidationError(
                f'Keys in evaluation models must be valid scan types. '
                f'Valid scan types are {scan_types}.'
            )
        # do we want to demand that every scan type has a chosen evaluation model?
        available_evaluation_models = ['MIQAMix-0', 'MIQAT1-0']
        if any(
            value is None or value not in available_evaluation_models
            for value in self.evaluation_models.values()
        ):
            raise ValidationError(
                f'Values in evaluation models must be valid evalution model names. '
                f'Valid evaluation model names are {available_evaluation_models}'
            )

        super().clean()

    def get_read_permission_groups(self):
        return ['collaborator', 'tier_1_reviewer', 'tier_2_reviewer']

    def get_review_permission_groups(self):
        return ['tier_1_reviewer', 'tier_2_reviewer']

    def get_user_role(self, user):
        perm_order = self.get_read_permission_groups()
        return sorted(
            get_perms(user, self),
            key=lambda perm: perm_order.index(perm) if perm in perm_order else -1,
        )[-1]

    def get_status(self):
        tier_2_reviewers = [
            user.id for user in get_users_with_perms(self, only_with_perms_in=['tier_2_reviewer'])
        ]
        scans_in_project = Scan.objects.filter(experiment__project=self)
        completed_scans_in_project = scans_in_project.alias(
            latest_decider_id=models.Subquery(
                ScanDecision.objects.filter(scan__id=models.OuterRef('id'))
                .order_by('-created')
                .values('creator_id')[:1]
            ),
            latest_decision=models.Subquery(
                ScanDecision.objects.filter(scan__id=models.OuterRef('id'))
                .order_by('-created')
                .values('decision')[:1]
            ),
        ).filter(models.Q(latest_decider_id__in=tier_2_reviewers) | models.Q(latest_decision='U'))

        return {
            'total_scans': scans_in_project.count(),
            'total_complete': completed_scans_in_project.count(),
        }

    def update_group(self, group_name, user_list):
        if group_name not in self.get_read_permission_groups():
            raise ValueError(f'Error: {group_name} is not a valid group on this Project.')

        old_list = get_users_with_perms(self, only_with_perms_in=[group_name])
        for previously_permitted_user in old_list:
            if previously_permitted_user.username not in user_list:
                remove_perm(group_name, previously_permitted_user, self)
                if 'reviewer' in group_name:
                    locked_experiments = apps.get_model('core', 'Experiment').objects.filter(
                        project=self, lock_owner=previously_permitted_user
                    )
                    for locked_experiment in locked_experiments:
                        locked_experiment.lock_owner = None
                        locked_experiment.save()

        for username in user_list:
            new_permitted_user = User.objects.get(username=username)
            if new_permitted_user not in old_list:
                assign_perm(group_name, new_permitted_user, self)

    class Meta:
        permissions = (
            ('collaborator', 'Collaborator'),
            ('tier_1_reviewer', 'Tier 1 Reviewer'),
            ('tier_2_reviewer', 'Tier 2 Reviewer'),
        )


@receiver(models.signals.post_delete, sender=Project)
def delete_objects(sender, instance, *args, **kwargs):
    from miqa.core import models

    models.Evaluation.objects.filter(frame__scan__experiment__project=instance).delete()
    models.ScanDecision.objects.filter(scan__experiment__project=instance).delete()
    models.Frame.objects.filter(scan__experiment__project=instance).delete()
    models.Scan.objects.filter(experiment__project=instance).delete()
    models.Experiment.objects.filter(project=instance).delete()
