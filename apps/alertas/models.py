"""Alertas e ações de resposta: dados do sistema, no PostgreSQL (decisão 007)."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Alerta(models.Model):
    class Nivel(models.TextChoices):
        ALTO = "ALTO", "Alto"
        MEDIO = "MÉDIO", "Médio"
        BAIXO = "BAIXO", "Baixo"

    class Status(models.TextChoices):
        ABERTO = "aberto", "Em aberto"
        MONITORANDO = "monitorando", "Monitorando"
        ENCERRADO = "encerrado", "Encerrado"

    class Origem(models.TextChoices):
        GATILHO = "gatilho", "Gatilho do sistema"
        INMET = "inmet", "Aviso oficial do INMET"
        MANUAL = "manual", "Registrado pela equipe"

    titulo = models.CharField(max_length=200)
    tipo = models.CharField(max_length=60)
    nivel = models.CharField(max_length=10, choices=Nivel.choices)
    distrito = models.CharField(max_length=40, help_text="DS I a DS VIII, ou Recife para a cidade toda")
    motivo = models.TextField(help_text="Por que o alerta foi gerado: os dados e o limiar usados")
    origem = models.CharField(max_length=10, choices=Origem.choices, default=Origem.GATILHO)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ABERTO)
    # identifica o mesmo alerta em coletas diferentes: gerar de novo atualiza, não duplica
    chave = models.CharField(max_length=200, unique=True)
    dados = models.JSONField(default=dict, blank=True, help_text="Dados que motivaram o alerta")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"[{self.nivel}] {self.titulo}"


class AcaoResposta(models.Model):
    class Status(models.TextChoices):
        ANDAMENTO = "andamento", "Em andamento"
        CONCLUIDA = "concluida", "Concluída"

    alerta = models.ForeignKey(Alerta, null=True, blank=True, on_delete=models.SET_NULL, related_name="acoes")
    nome = models.CharField(max_length=200)
    equipe = models.CharField(max_length=120, default="Equipe designada")
    responsavel = models.CharField(max_length=120, blank=True, help_text="Vira o usuário quando o login entrar")
    distrito = models.CharField(max_length=40)
    data = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ANDAMENTO)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def clean(self):
        if self.status == self.Status.CONCLUIDA and self.data and self.data > timezone.localdate():
            raise ValidationError({"data": "Uma ação concluída não pode ter data posterior a hoje."})

    def __str__(self):
        return self.nome
