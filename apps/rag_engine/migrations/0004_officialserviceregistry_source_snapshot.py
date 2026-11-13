from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('rag_engine', '0003_officialnews')]
    operations = [migrations.AddField(
        model_name='officialserviceregistry', name='source_snapshot',
        field=models.JSONField(default=dict, blank=True,
            help_text='Dossier de procédure recherché : informations, sources, formulaires et date de vérification.'),
    )]
