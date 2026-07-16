"""HTML/CSS helpers for cliente daily board cards."""
from __future__ import annotations

from html import escape

from services.clientes_board import ClienteCardPayload


def cliente_card_shell_html(payload: ClienteCardPayload) -> str:
    """Static header/body of a cliente card (widgets rendered separately in Streamlit)."""
    tipo = payload.tipo_relacion or "—"
    tipo_class = "cliente" if tipo == "Cliente" else "potencial"
    visto_class = " visto" if payload.visto_hoy else ""
    nombre = escape(payload.nombre)
    tipo_esc = escape(tipo)
    sensores = escape(str(payload.num_sensores))
    proxima = escape(payload.proxima_accion)
    incidencias = escape(payload.incidencias)

    return f"""
<article class="sanzar-cliente-card sanzar-cliente-card--{tipo_class}{visto_class}" aria-label="{nombre}">
  <div class="sanzar-cliente-card__top">
    <span class="sanzar-cliente-badge sanzar-cliente-badge--{tipo_class}">{tipo_esc}</span>
  </div>
  <h3 class="sanzar-cliente-card__title">{nombre}</h3>
  <dl class="sanzar-cliente-card__meta">
    <div><dt>Sensores</dt><dd>{sensores}</dd></div>
    <div><dt>Próxima acción</dt><dd>{proxima}</dd></div>
    <div><dt>Incidencias</dt><dd>{incidencias}</dd></div>
  </dl>
</article>
"""
