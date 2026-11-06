from django.contrib import admin

from .models import AcaoResposta, Alerta


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "nivel", "distrito", "origem", "status", "criado_em")
    list_filter = ("nivel", "origem", "status", "distrito")
    search_fields = ("titulo", "motivo")


@admin.register(AcaoResposta)
class AcaoRespostaAdmin(admin.ModelAdmin):
    list_display = ("nome", "equipe", "distrito", "data", "status", "alerta")
    list_filter = ("status", "distrito")
