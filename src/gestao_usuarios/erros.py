"""Erros da aplicação."""


class SessaoParada(RuntimeError):
    """Sessão do GRC expirada ou SAP indisponível: interrompe a rodada inteira. A solicitação fica pendente e é retomada na
    próxima varredura."""


class RequestBarrada(RuntimeError):
    """Uma trava impediu a request (nada foi enviado). Vira aviso no relatório; um humano decide."""


class UsuarioSemDadosNoGrc(RequestBarrada):
    """O GRC não preencheu First Name / Last Name / Email para o IGG (a pessoa não está no cadastro que o GRC consulta):
    esses campos são obrigatórios e vêm travados, então o Submit falharia."""


class ErroValidacaoGrc(RuntimeError):
    """O GRC recusou o Submit com erro de validação ('Enter the value for ...'): a request NÃO foi criada."""


class SubmitSemConfirmacao(RuntimeError):
    """Submit clicado, mas sem a mensagem de sucesso. NÃO repetir: a request pode ter sido criada. Conferir no Request Status."""
