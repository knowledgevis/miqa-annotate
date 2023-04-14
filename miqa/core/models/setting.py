from uuid import uuid4
from django.db import models
from django.db.models import Q

class Setting(models.Model):
    """Models an individual setting"""
    class Meta:
        ordering = ('key',)

    class SettingType(models.TextChoices):
        AOT = 'AOT', 'Anatomy Orientation'
        AT = 'AT', 'Artifact'
        DCT = 'DCT', 'Decision Choice'
        EFMMT = 'EFMMT', 'Evaluation File to Model Mapping'
        EMPT = 'EMPT', 'Evaluation Model Prediction'
        EMT = 'EMT', 'Evaluation Model'
        ST = 'ST', 'Scan'
        GIP = 'GIP', 'Global Import Path'
        GEP = 'GEP', 'Global Export Path'
        NS = 'NS', 'Not Set'
        GAOT = 'GAOT', 'Group of Anatomy Orientations'
        GAT = 'GAT', 'Group of Artifacts'
        GDCT = 'GDCT', 'Group of Decision Choices'
        GEFMMT = 'GEFMMT', 'Group of Evaluation File to Model Mappings'
        GEMPT = 'GEMPT', 'Group of Evaluation Model Predictions'
        GEMT = 'GEMT', 'Group of Evaluation Models'
        GST = 'GST', 'Group of Scans'


    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    key = models.CharField(max_length=255, blank=False)
    value = models.TextField(blank=True)
    type = models.CharField(
        max_length=20,
        choices=SettingType.choices,
        default=SettingType.NS,
     )
    group = models.ForeignKey('self', blank=True, on_delete=models.SET_NULL,
                              related_name='setting_group',
                              null=True,
                              limit_choices_to=Q(type__in=[SettingType.GST, SettingType.GAOT, SettingType.GAT, SettingType.GDCT, SettingType.GEFMMT, SettingType.GEMPT, SettingType.GEMT]))
    is_type = models.BooleanField(blank=True, null=False, default=False)

    def __str__(self):
        return str(self.key)
