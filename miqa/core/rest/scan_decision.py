from django_filters import rest_framework as filters
from guardian.shortcuts import get_objects_for_user, get_perms
from rest_framework import mixins, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from miqa.core.models import Project, Scan, ScanDecision
from miqa.core.models.scan_decision import ArtifactState
from miqa.core.rest.user import UserSerializer

from .permissions import UserHoldsExperimentLock, ensure_experiment_lock, has_review_perm


class ScanDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanDecision
        fields = [
            'id',
            'decision',
            'creator',
            'created',
            'note',
            'user_identified_artifacts',
            'location',
        ]
        read_only_fields = ['created', 'creator']
        ref_name = 'scan_decision'

    creator = UserSerializer()
    created = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')


class ScanDecisionViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    filter_backends = [filters.DjangoFilterBackend]
    permission_classes = [IsAuthenticated, UserHoldsExperimentLock]
    serializer_class = ScanDecisionSerializer

    def get_queryset(self):
        projects = get_objects_for_user(
            self.request.user,
            [f'core.{perm}' for perm in Project().get_read_permission_groups()],
            any_perm=True,
        )
        return ScanDecision.objects.filter(scan__experiment__project__in=projects)

    # cannot use project_permission_required decorator because no pk is provided
    def create(self, request, **kwargs):
        request_data = request.data
        scan = Scan.objects.get(id=request.data['scan'])

        if not has_review_perm(get_perms(request.user, scan.experiment.project)):
            return Response(status=status.HTTP_403_FORBIDDEN)

        request_data['scan'] = scan
        request_data['creator'] = request.user
        if (
            'artifacts' in request_data
            and 'present' in request_data['artifacts']
            and 'absent' in request_data['artifacts']
        ):
            request_data['user_identified_artifacts'] = {
                artifact_name: (
                    ArtifactState.PRESENT.value
                    if artifact_name in request_data['artifacts']['present']
                    else ArtifactState.ABSENT.value
                    if artifact_name in request_data['artifacts']['absent']
                    else ArtifactState.UNDEFINED.value
                )
                for artifact_name in scan.experiment.project.artifacts
            }
            del request_data['artifacts']

        ensure_experiment_lock(request_data['scan'], request_data['creator'])
        new_obj = ScanDecision(**request_data)
        new_obj.save()
        return Response(ScanDecisionSerializer(new_obj).data, status=status.HTTP_201_CREATED)
