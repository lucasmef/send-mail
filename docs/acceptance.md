# Critérios de aceitação

Executar testes automatizados com banco temporário, relógio controlável e transporte SMTP simulado. Não depender de internet, conta real ou Keychain pessoal para os testes da fila.

| ID | Requisitos | Cenário e resultado esperado |
|---|---|---|
| AC-01 | REQ-01,02 | JSON/CSV válido importa mensagens e retorna IDs/contagens em JSON; nenhum envio acontece. |
| AC-02 | REQ-02 | Um item inválido aborta toda a importação daquela chamada, apontando campo e item. |
| AC-03 | REQ-05 | Reimportar lote idêntico mantém a quantidade de registros; chave igual com outro conteúdo gera conflito. |
| AC-04 | REQ-03 | HTML e texto têm assinatura uma única vez; atualizar arquivo de assinatura não modifica registros anteriores. |
| AC-05 | REQ-06 | Preview não chama SMTP; scripts e recursos remotos não executam/carregam automaticamente. EML corresponde aos bytes persistidos. |
| AC-06 | REQ-05,06 | Teste vai somente ao destinatário indicado, tem novo Message-ID e não altera estado do original. Repetir request-id não repete envio. |
| AC-07 | REQ-07 | Execução limitada a duas mensagens distintas não inicia a terceira; retomar não zera orçamento. |
| AC-08 | REQ-07 | Pausa durante envio permite terminar o atual e impede o próximo. Pausa permanece após reinício. |
| AC-09 | REQ-04,05 | Segundo worker é recusado; duas importações concorrentes não criam duplicatas. |
| AC-10 | REQ-09 | Falha transitória segura grava próxima tentativa; reinício respeita horário e limite total de tentativas. |
| AC-11 | REQ-08,09 | Credencial inválida ou TLS não verificável bloqueia execução sem transmitir conteúdo nem expor senha. |
| AC-12 | REQ-10 | Queda antes de submission_started permite retry; queda depois desse marco, sem resultado persistido, produz uncertain. |
| AC-13 | REQ-10 | Servidor aceita e processo cai antes de gravar: retomada não reenvia automaticamente. |
| AC-14 | REQ-04,10 | Sucesso persistido seguido de falha em QUIT continua sent e nunca volta à fila. |
| AC-15 | REQ-07 | Sem cota diária local; retries/testes preservam limites por execução, marco de submissão e espera variável entre tentativas, inclusive após reinício. |
| AC-16 | REQ-01 | status retorna resumo sem corpos; erros têm código estável; stdout JSON não contém logs. |
| AC-17 | REQ-12 | Backup enquanto há atividade é íntegro e consultável; não contém credenciais. |
| AC-18 | REQ-10 | Decisão manual sobre uncertain preserva motivo/origem; resend cria item vinculado, idempotente e ainda pendente. |
| AC-19 | REQ-07 | Limites de tempo e tentativas encerram execução; mensagens restantes são preservadas para execução posterior. |
| AC-20 | REQ-05 | Repetir run com request-id existente retorna execução existente sem iniciar worker novo; parâmetros diferentes geram conflito. |
| AC-21 | REQ-08 | Backend inseguro/ausente é recusado e Keychain bloqueado retorna erro compreensível, sem fallback. |
| AC-22 | REQ-03,08 | Teste real autorizado para endereço do usuário confirma nome/endereço do remetente de domínio próprio, HTML e assinatura quando configurada, pelos campos exibidos no e-mail recebido. |

AC-22 é verificação manual opcional durante desenvolvimento e obrigatória antes da primeira operação real com destinatários externos. Requer conta configurada e autorização para o envio de teste. A execução dos demais cenários não autoriza enviar e-mails reais.

Casos de recuperação devem injetar interrupções nos limites das gravações e operações de rede, incluindo encerramento de subprocesso. Não basta testar apenas exceções capturadas dentro de uma única função.

## Evidências automatizadas — implementação v1

Execução em 2026-09-29, Python 3.13.14 no macOS. Todos os dados são fictícios, diretórios temporários e transportes simulados. A proteção autouse recusa criação acidental de smtplib.SMTP real. O driver de CLI em tests/cli_driver.py substitui sessão/credencial/relógio somente em testes, sem endpoint público alternativo.

| Cenários | Evidência |
|---|---|
| AC-01–04 | test_importer.py e test_composer.py: atomismo, CSV, IDs, assinatura e MIME congelado. |
| AC-05 | test_preview.py: sanitização/CSP e bytes EML. Inspeção visual limitada pela recusa de file: na ferramenta de navegador. |
| AC-06 | test_test_copy.py e test_end_to_end.py: cópia exclusiva e repetição idempotente. |
| AC-07–10 | test_controls.py, test_worker.py, test_importer.py e test_recovery.py: limites, pausa, SIGINT, concorrência e retry. |
| AC-11 | test_smtp.py, test_credentials.py e test_end_to_end.py: TLS/auth/Keychain e saída sanitizada. |
| AC-12–14 | test_recovery.py encerra subprocessos nos quatro marcos; test_smtp.py cobre queda durante DATA e QUIT. |
| AC-15 | test_controls.py, test_test_copy.py, test_regressions.py: quota compartilhada, retry, incerto e expiração. |
| AC-16 | test_cli.py, test_queries.py, test_end_to_end.py: JSON/erros/resumos sem corpos. |
| AC-17 | test_storage.py, test_regressions.py, test_end_to_end.py: backup ativo, íntegro e bloqueado para retomada. |
| AC-18 | test_recovery.py e test_regressions.py: histórico manual e reenvio novo/idempotente. |
| AC-19–20 | test_controls.py e test_worker.py: duração/tentativas e request-id. |
| AC-21 | test_credentials.py: backend nativo explícito, indisponível/negado/bloqueado e sem fallback. |
| AC-22 | **Concluído.** SMTP 250 e imagens do usuário confirmam recebimento, HTML e nome/endereço do remetente de domínio próprio. Assinatura não configurada; cabeçalhos técnicos de autenticação não inspecionados. |

Comandos de verificação e contagens finais ficam no registro de T13 em TASKS.md. Simulações não comprovam permissões do remetente no iCloud nem aparência no cliente de e-mail.

Resultado final T13: **66 testes passaram** no ambiente do projeto e novamente em instalação limpa pelo wheel. Naquela etapa T14 estava bloqueada. Posteriormente, AC-22 foi concluído por envio real e imagens do recebimento.

## AC-23 — Configuração mínima e assinatura posterior

Setup novo solicita apenas e-mail e senha, permite compor sem assinatura e preserva preferências ao ser repetido. `signature` configura HTML/texto depois, sem Keychain; a versão texto é gerada quando omitida. Alterar/remover assinatura não muda MIME já importado e não duplica reimportações. Arquivo inválido preserva a configuração anterior.

## AC-24 — Nomes por mensagem e identidade padrão

Alterar remetente/nome não modifica login, senha ou mensagens já importadas. Nome padrão e override por mensagem sobrevivem à codificação MIME, inclusive acentos/vírgulas; envelope mantém endereços simples. Rejeitar CR/LF. Reenvio preserva nomes originais; cópia de teste remove nome do destinatário original ao substituir o destino. CSV aceita nomes opcionais e mantém compatibilidade com o formato anterior.

## AC-25 — Remoção da cota diária e intervalo variável

Mais de 100 mensagens podem ser aceitas no mesmo dia quando os limites explícitos da execução permitem. daily_budget legado não bloqueia. Esperas sorteadas persistem entre processos/execuções e são medidas após o término da tentativa anterior. Throttling do SMTP continua bloqueando novas execuções. Migração preserva envios existentes e remove apenas cooldowns da cota local.

## AC-26 — Troca para KingHost

Perfil KingHost usa SMTP_SSL na porta 465, verificando certificado antes de acessar credencial. Doctor não submete mensagem. Falha de certificado bloqueia autenticação. Troca sem --replace-account é recusada; troca explícita preserva histórico/assinatura e não envia a fila da conta antiga. Autenticação e envio reais só podem ser declarados verificados depois da configuração da senha e teste autorizado.

## AC-27 — Confiança TLS independente do bundle antigo do sistema (REQ-08)

O contexto SMTP carrega as autoridades distribuídas com certifi mesmo quando o arquivo padrão do sistema está vazio. Mantém CERT_REQUIRED e check_hostname. Certificado inválido continua impedindo acesso à credencial (AC-26). Testes automatizados não acessam rede.

## AC-28 — DKIM local (REQ-15)

Chave privada nunca gravada em configuração/saídas; setup idempotente. Assinatura RSA-SHA256 válida cobre remetente, destinatário, assunto, data, Message-ID e corpo MIME; adulteração falha. Registro DNS incompatível/ausente impede ativação; pendência, domínio diferente ou chave ausente bloqueiam envio antes de DATA. Perfil sem DKIM mantém comportamento anterior. Provedor pode adicionar cabeçalhos sem invalidar assinatura. Testes usam chaves efêmeras e DNS/SMTP/Keychain simulados; teste real depende de publicação DNS.

AC-28: verificação real concluída em 2026-09-30. Usuário confirmou recebimento na entrada; cabeçalhos do iCloud mostram DKIM pass para example.com com rsa-sha256, SPF pass, DMARC pass e destino INBOX. KingHost preservou a assinatura local. Resultado de um teste, sem garantia de classificação futura; assinatura legada do provedor continua inválida.

## AC-29 — Arquivo IMAP após SMTP (REQ-16)

Serviços simulados: bytes arquivados iguais aos transmitidos, com DKIM, nomes, destinatário, assunto e assinatura. Apenas após SMTP positivo e commit sent. SMTP rejeitado/incerto não cria arquivo. Falha/rejeição/desconexão/logout IMAP preserva sent e não chama SMTP de novo. Retry explícito reconcilia Message-ID exato (não substring), não duplica, preserva pasta original e recusa conta diferente. Quedas antes/depois de APPEND e antes do commit archived são exercitadas em subprocessos; possível aceitação com busca vazia fica uncertain. Migração preserva dados históricos e não os arquiva; fila pendente não muda. Configuração verifica TLS antes da senha, descoberta por \Sent ou escolha explícita; nunca presume/cria pasta implicitamente.

## AC-30 — Configuração real sem envio (REQ-16)

Verificar conta KingHost por TLS, Keychain, LIST e EXAMINE; documentar pasta e preservar fila. Não chamar SMTP DATA nem IMAP APPEND. Configuração verificada não significa arquivamento real testado nem prova exibição no cliente. Primeiro arquivo real aguarda próximo envio autorizado na conversa original.

Evidências AC-29/30 — 2026-09-30: 113 testes passaram, com 21 cenários novos em test_archiving.py e imap_crash_driver.py (quatro interrupções de processo; DKIM real com chave efêmera; SMTP/IMAP simulados). Conta real: TLS, autenticação, LIST, criação/subscrição explícita de INBOX.Sent e EXAMINE passaram; nenhum APPEND/SMTP. Hash de todos os registros preservado, 114 mensagens ainda pending. T18 permanece pendente: arquivo real e exibição como Enviados nos clientes dependem do próximo envio autorizado.

## AC-31 — Primeiro arquivo IMAP real autorizado (REQ-16)

Após autorização explícita de um teste ao iCloud do usuário, SMTP aceita uma única cópia e o arquivo é aceito pelo IMAP. Busca por Message-ID exato encontra somente uma cópia; FETCH BODY.PEEK[] confirma bytes iguais aos transmitidos, preservando cabeçalhos, assinatura HTML e DKIM local. A fila de prospecção permanece idêntica. Confirmação visual no webmail/Mail e recebimento no destino são verificações separadas.

Concluído em 2026-09-30: id-operacional-anonimizado, SMTP 250/sent, archive=archived, INBOX.Sent UID 1, UIDVALIDITY 1790778297, uma cópia exata, DKIM local válido. 114 registros pending intactos por hash. Nenhum inbox iCloud consultado; recebimento/apresentação visual aguardam usuário. Evidências e autorização registradas em T18.

AC-31 — confirmação final em 2026-09-30: usuário confirmou recebimento do teste, envio e arquivamento correto na pasta Enviados. Verificação real e visual concluída, conforme confirmação expressa na conversa original.
