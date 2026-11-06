from django.core.management.base import BaseCommand

from apps.alertas.servicos import gerar_alertas


class Command(BaseCommand):
    help = "Grava no PostgreSQL os alertas do dia (gatilhos do sistema e avisos do INMET)."

    def handle(self, *args, **opcoes):
        r = gerar_alertas()
        self.stdout.write(self.style.SUCCESS(f"alertas: {r['novos']} novos, {r['atualizados']} atualizados"))
