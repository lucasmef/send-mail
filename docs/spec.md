# Especificação funcional — v1

Estado: v1 implementada; validação automatizada com transporte simulado. Integração real confirmada por envio e imagens do recebimento (AC-22), sem assinatura personalizada. Data: 2026-09-29.

## Escopo

Uma conta ativa (iCloud ou KingHost), um remetente inicialmente igual ao login (domínio próprio autorizado é opcional), um Mac e normalmente até 100 mensagens por dia. Um destinatário por mensagem, sem CC/BCC, anexos ou agendamento na v1.

## Requisitos

| ID | Requisito |
|---|---|
| REQ-01 | A IA pode preparar um lote e operar todas as funções ordinárias pela CLI com saída JSON. |
| REQ-02 | Importar JSON e CSV com destinatário, assunto, conteúdo HTML e ID estável por item. |
| REQ-03 | Compor texto simples e HTML com assinatura opcional; congelar o conteúdo final na importação. |
| REQ-04 | Manter fila e histórico persistentes, com consulta por lote, execução, mensagem e estado. |
| REQ-05 | Evitar duplicatas ao repetir importação, comando de início ou retomada. |
| REQ-06 | Oferecer preview local sem envio e envio de teste separado para endereço explícito. |
| REQ-07 | Iniciar, pausar e retomar, com limite de mensagens, tentativas e duração. |
| REQ-08 | Enviar por SMTP autenticado com TLS obrigatório, recuperando senha das Chaves do macOS. |
| REQ-09 | Repetir somente falhas comprovadamente seguras, persistindo próxima tentativa. |
| REQ-10 | Recuperar interrupções sem esquecer resultados; isolar resultados incertos. |
| REQ-11 | Instalar e operar sem infraestrutura externa além do provedor de e-mail existente. |
| REQ-12 | Fornecer exportação e backup consistente do estado. |

## Preparação dos e-mails

- O importador aceita conteúdo final, sem executar templates, código ou expressões.
- Personalização é feita pela IA antes da importação. Assinatura é adicionada pelo programa, uma vez. Um sufixo exato igual à assinatura configurada é preservado sem repetição; `text` vazio equivale a ausente.
- São obrigatórios `external_id`, `to`, `subject`, `html`. `text` é opcional; na ausência, uma conversão determinística produz texto simples preservando parágrafos e links quando possível.
- Setup solicita apenas e-mail e senha de aplicativo e cria assinatura vazia. `signature --html ARQUIVO [--text ARQUIVO]` configura depois; `signature --clear` remove. Gerar texto simples quando omitido. Alterações valem apenas para novas importações. Repetir setup preserva preferências existentes. Não buscar recursos remotos ao compor.
- A composição usa MIME `multipart/alternative`, UTF-8 e `Message-ID` persistente. Os bytes finais são persistidos para reutilização.
- Mesma chave com conteúdo diferente gera conflito. Correção usa novo ID explícito e cancelamento do registro anterior; a v1 não tem edição de mensagem importada.
- Importação é atômica: qualquer item inválido ou conflito aborta o lote importado naquele comando, sem inserções parciais.
- A validação rejeita CR/LF em campos de cabeçalho, múltiplos destinatários e sintaxe inválida. Não promete verificar a existência da caixa postal.
- Endereços com parte local não ASCII ficam fora da v1. Domínios internacionais são convertidos para IDNA; a parte local é preservada, sem remover pontos ou sufixos `+`.

## Operação

Default: concorrência 1 e espera sorteada uniformemente entre 15 e 45 segundos após cada tentativa SMTP. Sem limite diário local. Persistir a espera sorteada na tentativa; pausa, nova execução e reinício respeitam o mesmo prazo, sem sortear novamente. As durações variam, embora um sorteio possa eventualmente repetir um valor.

`run` exige lote e limite explícitos. Um limite de 20 significa até 20 mensagens distintas iniciadas nessa execução; mensagens incertas consomem esse limite. Retries da mesma mensagem não consomem outro slot de mensagem, mas consomem tentativas da execução.

Continuar registrando o marco persistente de submissão antes de transmitir conteúdo para permitir recuperação segura. O campo legado daily_budget é aceito, mas não aplicado. interval_min_seconds e interval_max_seconds configuram a faixa, com 15 <= mínimo < máximo <= 86400 segundos. Configurações antigas com interval_seconds usam esse valor como mínimo e máximo igual ao maior entre 45 e mínimo + 30.

Pausa é cooperativa: concluir a operação SMTP atual e não iniciar outra. `Ctrl+C` solicita a mesma pausa; encerramento abrupto segue as regras de recuperação. Suspensão do Mac não torna a fila inválida; conexões interrompidas são classificadas antes de continuar.

O tempo máximo de execução conta apenas períodos ativos, persiste entre retomadas e inclui esperas por retry. Contabilizar tempo de forma monotônica durante o processo; na queda, usar o último checkpoint persistido. Reiniciar não renova os limites. Após crash ou reboot, o programa aguarda `resume` explícito.

Defaults de uma execução: até cinco tentativas totais por mensagem, 100 tentativas por execução e 60 minutos ativos. Os limites por execução podem ser ajustados explicitamente. Ao esgotar um limite, encerrar a execução como `limit_reached`; itens ainda elegíveis podem entrar em nova execução explícita, mantendo o histórico e o total de tentativas da mensagem.

## Fora do escopo inicial

Interface gráfica, servidor HTTP/MCP, integração com APIs de IA, envio paralelo, anexos, múltiplas contas, campanhas de marketing, leitura de inbox, rastreamento de abertura, bounces automáticos e serviço permanente após login.

Não prometer entrega exatamente uma vez, recebimento na caixa de entrada ou retomada enquanto o Mac estiver desligado.

Throttling explícito suspende a conta por ao menos uma hora e exige retomada explícita após a espera/correção. Iniciar outra execução não ignora suspensão imposta pelo provedor.

## Nomes e remetente configuráveis

`sender --email EMAIL --name NOME` permite alterar remetente padrão sem modificar login ou senha. O endereço precisa estar autorizado na conta iCloud. `sender_name` e `to_name` são opcionais por mensagem; nomes são validados contra injeção de cabeçalhos e codificados pela biblioteca de e-mail. O envelope SMTP continua usando endereços simples. Mudanças de padrão não modificam mensagens importadas. O cliente de quem recebe pode substituir o nome exibido pelo nome salvo nos contatos.

## Provedor KingHost

Setup aceita --provider kinghost --email EMAIL --sender-name NOME --replace-account. Solicita senha somente no Terminal; mantém assinatura, limites e histórico, mudando conta ativa/remetente. Troca é explícita e protegida pelo lock do worker. Mensagens antigas não são reenviadas pela nova conta. Perfil KingHost direto usa smtp.kinghost.net:465 com TLS implícito e certificado verificado; não reutilizar senha iCloud. Perfil antigo sem provider continua iCloud. Diagnóstico sem envio; autenticação real KingHost aguarda a senha local.

### Autoridades TLS (REQ-08)

Ambos os provedores usam o bundle público do certifi distribuído com a aplicação, com validação obrigatória de cadeia e hostname antes de acessar a senha. Falha de validação continua retornando TLS_INVALID e bloqueando autenticação.

## REQ-15 — DKIM local opcional

Preparar chave RSA 2048 no Keychain e registro TXT público, sem enviar. Ativação exige prova criptográfica usando a chave publicada no DNS. Assinar com rsa-sha256 e domínio exato do remetente antes de DATA, inclusive mensagens já importadas. Conteúdo MIME persistido permanece congelado; DKIM é um cabeçalho de transporte calculado por tentativa. Falha de chave, domínio ou assinatura bloqueia antes da submissão; não enviar sem assinatura quando configurada. Configuração pendente bloqueia envio até ativação ou desativação explícita.

## REQ-16 — Cópia IMAP após envio

KingHost direto admite arquivo opcional em imap.kinghost.net:993 com TLS/certificado verificado e senha exclusivamente no Keychain nativo. Descobrir pasta por LIST e \Sent; sem indicação única, exigir seleção explícita. Não inferir nome nem criar pasta silenciosamente. Ativação vale para futuras aceitações SMTP, inclusive mensagens já pendentes e novos testes. Não alterar mensagens existentes nem arquivar histórico ou decisões manuais automaticamente.

Gravar sent e solicitação do arquivo atomicamente depois de SMTP positivo. Arquivar os mesmos bytes transmitidos, incluindo DKIM local, MIME, assinatura e nomes. Falha de arquivo mantém sent e jamais chama SMTP novamente. Retry explícito atua somente no arquivo. Persistir início de APPEND; reconciliação compara Message-ID exato na pasta original. Se APPEND puder ter sido aceito, ausência na busca não prova rejeição: conservar uncertain e nunca repetir APPEND automaticamente. Mais de uma cópia detectada requer atenção.
