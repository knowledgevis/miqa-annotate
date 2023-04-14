from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    from miqa.core.models import Experiment

DECISION_CHOICES = [
    ('U', 'Usable'),
    ('UE', 'Usable-Extra'),
    ('Q?', 'Questionable'),
    ('UN', 'Unusable'),
]


class ArtifactState(Enum):
    PRESENT = 1
    ABSENT = 0
    UNDEFINED = -1


class ScanDecision(models.Model):
    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['scan', '-created']),
        ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created = models.DateTimeField(default=timezone.now, null=True)
    scan = models.ForeignKey('Scan', related_name='decisions', on_delete=models.CASCADE)
    creator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    decision = models.CharField(max_length=2, choices=DECISION_CHOICES, blank=False)
    note = models.TextField(max_length=3000, blank=True)
    user_identified_artifacts = models.JSONField(default=dict)
    location = models.JSONField(default=dict)

    @property
    def experiment(self) -> Experiment:
        return self.scan.experiment
