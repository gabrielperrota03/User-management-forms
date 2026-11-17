"""Erros que interrompem a rodada inteira (não só uma solicitação)."""


class SessaoParada(RuntimeError):
    """Sessão do GRC expirada ou SAP indisponível: a solicitação fica pendente e é retomada na próxima varredura."""
