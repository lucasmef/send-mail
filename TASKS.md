# Fila de implementação — GPT Sol

Andamento: T01–T18 concluídas; primeiro arquivo IMAP real conferido por leitura da pasta. Recebimento do novo teste no iCloud e apresentação da pasta nos clientes aguardam confirmação visual do usuário. Registros abaixo preservam o histórico das etapas.

Esta é a fila executável do projeto. `docs/implementation-plan.md` mantém a visão por etapas; este arquivo é a fonte de verdade para o andamento de cada tarefa.

## Instrução para o executor

Leia `AGENTS.md`, `README.md` e a documentação indicada na tarefa. Execute esta fila em ordem, começando pela primeira tarefa pendente cujas dependências estejam concluídas. Implemente, verifique e registre evidências antes de marcar uma tarefa como concluída. Continue para a próxima tarefa sem solicitar confirmação para decisões rotineiras já cobertas pelo escopo.

Trabalhe neste projeto, sem criar chats ou delegar tarefas automaticamente. Não amplie a arquitetura. Não envie e-mails reais durante desenvolvimento: use transporte simulado e dados fictícios. A autorização para implementar não é autorização para enviar mensagens reais.

Se houver contradição documental, resolva a menor ambiguidade compatível com a intenção do usuário e registre a decisão junto da alteração da especificação. Pergunte somente se a escolha mudar materialmente o comportamento esperado ou exigir informação indisponível. Bloqueios de credenciais ou do teste real não impedem concluir tarefas independentes.

Não implemente todas as tarefas antes de verificar: conclua e valide cada unidade. Se a sessão for interrompida, deixe neste arquivo o próximo passo exato.

## Estados e conclusão

Estados: `pendente`, `em_andamento`, `bloqueada`, `concluida`.

Uma tarefa só fica `concluida` quando os entregáveis existem, as verificações passaram e as evidências foram registradas. Código escrito sem verificação não conta como conclusão. Marque no máximo uma tarefa `em_andamento`.

Ao encerrar cada tarefa, atualize a tabela e acrescente ao registro de execução: arquivos relevantes, comando de verificação, resultado, cenários AC cobertos e limitações. Marque também os checkboxes correspondentes no plano de implementação, apenas quando todos os seus requisitos forem atendidos.

## Ordem de execução

| ID | Tarefa | Depende de | Estado |
|---|---|---|---|
| T01 | Base Python e contrato de saída | — | concluida |
| T02 | SQLite, migrações e backup | T01 | concluida |
| T03 | Composição MIME e assinatura | T01 | concluida |
| T04 | Importação JSON/CSV idempotente | T02, T03 | concluida |
| T05 | Consulta, cancelamento e exportação | T04 | concluida |
| T06 | Preview HTML protegido e EML | T03, T05 | concluida |
| T07 | Execuções e worker simulado | T02, T05 | concluida |
| T08 | Pausa, limites e retry persistente | T07 | concluida |
| T09 | Recuperação de quedas e resultados incertos | T08 | concluida |
| T10 | Setup e Chaves do macOS | T01, T02 | concluida |
| T11 | Transporte SMTP e diagnóstico | T09, T10 | concluida |
| T12 | Envio de teste idempotente | T11 | concluida |
| T13 | Fluxo completo e entrega operacional | T06, T12 | concluida |
| T14 | Verificação real com o usuário | T13 + configuração/autorização | concluida |
| T15 | DKIM local | T14 | concluida |
| T16 | Arquivamento IMAP KingHost | T15 | concluida |
| T17 | Configuração IMAP real sem envio | T16 | concluida |
| T18 | Primeiro arquivamento real autorizado | T17 + autorização explícita de teste | concluida |

## T01 — Base Python e contrato de saída

**Ler:** `docs/cli.md`, `docs/architecture.md`.

**Entregar:** pacote instalável, `pyproject.toml`, `.python-version`, `uv.lock`, comando `mailqueue`, diretório de dados configurável, leitura de configuração, envelope JSON e códigos de erro/saída. Não expor comandos incompletos como funcionais.

**Verificar:** instalação local isolada, `--help`, rejeição de argumentos inválidos, saída JSON sem logs misturados e uso de diretório temporário. Cobertura inicial de AC-16; completar em T05/T07.

**Pronto quando:** a CLI funciona no ambiente do projeto e os testes de contrato passam sem rede ou credenciais.

## T02 — SQLite, migrações e backup

**Ler:** `docs/persistence.md`.

**Entregar:** tabelas `messages`, `attempts`, `runs`, controle de migrações, índices, restrições, configuração de durabilidade, permissões e comando `backup`. Adicionar campos auxiliares somente quando necessários ao contrato e documentá-los.

**Verificar:** migração repetível sem perda de dados, restrições de unicidade, rollback e backup íntegro durante gravações. AC-17.

**Pronto quando:** abrir/reabrir o banco preserva estado e um backup pode ser consultado independentemente, sem tratar backup antigo como fila segura para retomar envios.

## T03 — Composição MIME e assinatura

**Ler:** REQ-03 em `docs/spec.md`, modelo de mensagens em `docs/persistence.md`.

**Entregar:** validação de remetente/destinatário/cabeçalhos, composição de texto e HTML com assinatura, Message-ID estável, hashes canônicos e bytes MIME. Composição deve ser utilizável sem SMTP e sem Keychain.

**Verificar:** acentos, HTML, conversão para texto, assinatura uma vez, cabeçalhos com CR/LF recusados, domínio IDNA e rejeição de endereços fora do escopo. Parte de AC-04.

**Pronto quando:** MIME pode ser lido de volta pela biblioteca de e-mail com as partes, cabeçalhos e conteúdo esperados.

## T04 — Importação JSON/CSV idempotente

**Ler:** `docs/cli.md`, REQ-02/03/05, regras de hash em `docs/persistence.md`.

**Entregar:** `validate` e `import`, lote atômico, erros por item/campo, detecção de chaves conflitantes e reutilização de mensagens já importadas. Usar o compositor de T03.

**Verificar:** AC-01 a AC-04; CSV com vírgulas/aspas/quebras de linha no conteúdo; duplicatas dentro do próprio arquivo; importações concorrentes; nova assinatura sem alteração de registros existentes. Parte de AC-09.

**Pronto quando:** repetir uma importação não aumenta a fila e qualquer erro aborta somente as alterações daquela chamada.

## T05 — Consulta, cancelamento e exportação

**Ler:** contrato dos comandos em `docs/cli.md`.

**Entregar:** `list` paginado, `show`, `cancel`, `export`, resumos de estados e corpo somente sob solicitação explícita. `status --run` será integrado em T07.

**Verificar:** paginação estável, filtros, registros inexistentes, cancelamento inelegível recusado, exportação fiel e ausência de corpos/segredos nos resumos. Parte de AC-16.

**Pronto quando:** uma IA consegue inspecionar e organizar a fila somente pela CLI, sem SQL ou edição de arquivos de estado.

## T06 — Preview HTML protegido e EML

**Ler:** ADR-006 em `docs/architecture.md`, AC-05.

**Entregar:** exportação HTML e EML para caminhos absolutos, sem abrir automaticamente um app e sem alterar a mensagem congelada.

**Verificar:** AC-05, incluindo scripts, atributos de eventos, formulários, frames, meta refresh e recursos remotos em imagens/CSS. Validar o comportamento do HTML em navegador local com conteúdo fictício quando houver ferramenta disponível; registrar separadamente qualquer limitação de verificação visual. EML deve coincidir byte a byte com o armazenado.

**Pronto quando:** preview não dispara SMTP nem conteúdo ativo. Se o bloqueio não puder ser garantido, restringir o HTML exibido de forma segura e documentar a limitação visual.

## T07 — Execuções e worker simulado

**Ler:** `docs/persistence.md` e contratos `run`, `status`, `resume` em `docs/cli.md`.

**Entregar:** interface mínima de transporte substituível em testes, worker sequencial, lock de sistema operacional, reserva transacional, execuções com request-id e contadores, transições básicas e resumo de execução. Transporte simulado pertence aos testes, sem adicionar endpoint de envio público alternativo.

**Verificar:** AC-09, AC-20 e parte de AC-16; usar processos distintos para comprovar exclusão do worker. Repetir `run` retorna o recurso existente e não executa novos envios.

**Pronto quando:** uma fila fictícia percorre o worker sem rede e uma segunda execução concorrente não envia.

## T08 — Pausa, limites e retry persistente

**Ler:** controles operacionais de `docs/spec.md` e regras de retry em `docs/persistence.md`.

**Entregar:** pausa cooperativa, Ctrl+C, retomada, intervalo entre tentativas, limite de mensagens distintas, total de tentativas, duração ativa e orçamento móvel de 24 horas. Persistir reservas e próxima tentativa antes das ações correspondentes.

**Verificar:** AC-07, AC-08, AC-10, AC-15 e AC-19 com relógio controlável, sem esperas reais longas. Cobertura de testes reais de envio de teste em AC-15 será completada em T12.

**Pronto quando:** pausa/reinício não renovam orçamento, retries respeitam espera e itens não processados continuam disponíveis conforme o contrato.

## T09 — Recuperação de quedas e resultados incertos

**Ler:** ciclo e retomada em `docs/persistence.md`, comandos `resolve` em `docs/cli.md`.

**Entregar:** recuperação por fase persistida, estado `uncertain`, interrupção ao falhar gravação de sucesso e resolução manual auditável. Reenvio deliberado cria outro registro idempotente ainda pendente.

**Verificar:** AC-12, AC-13, AC-14 e AC-18; encerrar subprocessos antes/depois da reserva de submissão e após aceitação simulada. Verificar que `sent` jamais volta à fila e que resultado incerto não recebe retry automático.

**Pronto quando:** todos os pontos de queda relevantes têm comportamento demonstrado, sem depender apenas de exceções capturadas em testes unitários.

## T10 — Setup e Chaves do macOS

**Ler:** ADR-004 e requisitos de segurança em `AGENTS.md`.

**Entregar:** configuração inicial de conta/remetente/assinatura e acesso explícito ao backend macOS via `keyring`. Senha solicitada sem eco, sem argumentos de CLI, sem arquivos ou logs. Não tocar na conta/Keychain pessoal durante testes automatizados.

**Verificar:** AC-21 com backend simulado; erros de permissão, chaveiro bloqueado, backend indisponível e ausência de fallback. Conferir captura de stdout/stderr para impedir vazamento.

**Pronto quando:** configuração segura é implementada e erros são compreensíveis; configuração real pelo usuário pode permanecer pendente até T14.

## T11 — Transporte SMTP e diagnóstico

**Ler:** ADR-003, `docs/persistence.md`, documentação oficial atual de SMTP/iCloud.

**Entregar:** transporte por `smtplib`, TLS obrigatório e verificado antes de autenticar, timeouts por fase, callbacks/eventos mínimos para marcos persistentes e `doctor` sem envio. Integrar ao worker já validado.

**Verificar:** AC-11 e regressão de AC-12 a AC-14 contra sessão SMTP simulada: 4xx, 5xx, rejeição de remetente, falha de certificado, STARTTLS indisponível, queda durante DATA, resposta positiva e falha em QUIT. Não basta simular apenas o resultado final do transporte.

**Pronto quando:** classificação de falhas reais do adaptador preserva as garantias de recuperação e nenhum teste usa o SMTP pessoal.

## T12 — Envio de teste idempotente

**Ler:** comando `test` e seus limites em `docs/cli.md` e `docs/spec.md`.

**Entregar:** cópia com destinatário explícito e novo Message-ID, vínculo ao original, request-id único e uma única tentativa por comando. Reutilizar lock, orçamento e persistência; não criar um caminho de envio que ignore o worker.

**Verificar:** AC-06 e completar AC-15, incluindo repetição de request-id, parâmetros conflitantes, destino original ausente do envelope e do cabeçalho To, quota esgotada e resultado incerto.

**Pronto quando:** testar uma mensagem não altera nem envia a mensagem original, e repetir o comando não repete o teste.

## T13 — Fluxo completo e entrega operacional

**Ler:** todos os contratos e `docs/acceptance.md`.

**Entregar:** teste ponta a ponta da CLI com transporte simulado e diretório temporário; exemplos fictícios; instruções curtas de operação para IA; instalação reproduzível, atualização e backup documentados. Atualizar README, plano e status dos cenários.

**Verificar:** suite automatizada completa, instalação em ambiente limpo, todos os AC-01 a AC-21 cobertos e fluxo importar → preview → teste simulado → run → pausa → resume → status → export → backup. Revisar vazamento de dados e divergências entre ajuda/CLI/documentação.

**Pronto quando:** solução utilizável pela CLI está entregue, com pendências reais explicitadas. Não declarar integração iCloud verificada se T14 não ocorreu.

## T14 — Verificação real com o usuário

**Pré-condições:** implementação concluída, conta configurada, endereço de teste fornecido e autorização explícita para enviar a cópia de teste. Não solicitar senha no chat; usar o setup local.

**Entregar:** executar `doctor`, gerar preview, enviar uma única cópia de teste ao endereço autorizado e registrar o resultado sem credenciais ou corpo pessoal na documentação do repositório.

**Verificar:** AC-22. Confirmação SMTP comprova aceitação apenas; aparência, assinatura, remetente e cabeçalhos recebidos precisam ser conferidos no e-mail recebido pelo usuário. Não adicionar leitura de inbox à v1 para realizar este teste.

**Pronto quando:** usuário confirma o recebimento e a composição esperada, ou evidência equivalente autorizada é obtida. Sem essas condições, marcar `bloqueada`, explicar exatamente o que falta e manter T01–T13 concluídas quando aplicável.

## Registro de execução

Tarefa: T01
Estado: concluida
Alterações: pyproject.toml, .python-version, uv.lock, src/mailqueue/{cli,config,errors}.py, tests/test_cli.py.
Verificação: uv sync; uv run pytest -q (3 passed); uv run mailqueue --help (exit 0). Ambiente .venv isolado com Python 3.13.14.
Aceitação: AC-16 parcial: envelope v1, erro INVALID_ARGUMENT e stdout sem logs; consultas serão verificadas em T05/T07.
Decisões: comandos incompletos não são expostos. Nenhuma rede SMTP ou credencial usada.
Próximo passo: T02, persistência e backup.


Modelo para cada registro:

```text
Tarefa: Txx
Estado: concluida | bloqueada | em_andamento
Alterações: arquivos e comportamento entregue
Verificação: comando executado e resultado observado
Aceitação: AC-xx cobertos; lacunas restantes
Decisões: alterações de contrato, se houver
Próximo passo: ação concreta para continuar
```

Tarefa: T02
Estado: concluida
Alterações: storage.py, migrations/001_initial.sql, comando backup, tests/test_storage.py e docs/persistence.md.
Verificação: uv run pytest -q — 5 passed, incluindo rollback, reabertura, permissões e backup durante gravações por outra conexão.
Aceitação: AC-17. Unicidade de IDs/chaves definida no schema; concorrência de importação será exercitada em T04.
Decisões: backup recebe sending_blocked na tabela técnica schema_migrations; worker deverá recusá-lo. Destino existente não é sobrescrito.
Próximo passo: T03, composição independente de SMTP/Keychain.

Tarefa: T03
Estado: concluida
Alterações: composer.py e tests/test_composer.py.
Verificação: uv sync --reinstall-package send-mailqueue reparou descoberta editável; uv run pytest -q — 14 passed. MIME relido com biblioteca padrão, assinatura única, acentos, texto e links, IDNA, rejeição CR/LF e endereços fora do escopo.
Aceitação: AC-04 parcial; congelamento após atualização da assinatura será verificado em T04.
Decisões: assinatura já presente como sufixo exato não é acrescentada novamente; campos text vazios equivalem a ausentes.
Próximo passo: T04, importação atômica e concorrente.

Tarefa: T04
Estado: concluida
Alterações: importer.py, validate/import na CLI, fixtures fictícias e test_importer.py.
Verificação: uv sync --reinstall-package send-mailqueue; uv run pytest -q — 17 passed. Importação/validação, rollback de conflito tardio, erros por item, CSV com aspas/vírgulas/quebras, duplicatas e processos concorrentes.
Aceitação: AC-01 a AC-04; AC-09 concorrência de importação. Assinatura alterada não modifica MIME já congelado.
Decisões: JSON com chaves repetidas é recusado; duplicatas idênticas no mesmo arquivo reaproveitam registro.
Limitações: ambiente de execução tem perdido descoberta do .pth entre chamadas; reinstalação editável antes dos testes funciona. Instalação não editável será verificada em T13.
Próximo passo: T05, consulta e organização sem corpos nos resumos.

Tarefa: T05
Estado: concluida
Alterações: queries.py, list/show/cancel/export na CLI e test_queries.py.
Verificação: uv sync --reinstall-package send-mailqueue; uv run pytest -q — 18 passed. Paginação sem repetição, filtros, ausência de corpos, registro inexistente, cancelamento repetido recusado, exportação fiel e saída CLI JSON.
Aceitação: AC-16 para consultas; status será integrado em T07.
Decisões: cancelamento recusa qualquer item já submetido, inclusive retry_wait; destinos de exportação existentes não são sobrescritos.
Próximo passo: T06, preview HTML protegido e EML.

Tarefa: T06
Estado: concluida
Alterações: preview.py, comando preview, test_preview.py, ADR-006 e contrato de saída.
Verificação: uv run pytest -q — 20 passed após correção da sintaxe CSP. EML idêntico aos bytes persistidos; HTML auditado com HTMLParser contra scripts/eventos/formulários/frames/meta refresh/imagens/CSS remotos.
Aceitação: AC-05; sem tentativas SMTP e sem alteração do original.
Decisões: sanitizador com lista positiva sem CSS/mídia; visual aproximado documentado.
Limitações: tentativa de inspeção visual por navegador local recusada pela política da ferramenta (protocolo file: não permitido). Nenhuma inspeção visual concluída; sanitização restritiva verificada automaticamente.
Próximo passo: T07, worker e exclusão em processos distintos.

Tarefa: T07
Estado: concluida
Alterações: worker.py, interface DeliveryError/transport, status na CLI e test_worker.py.
Verificação: uv run pytest -q — 22 passed. Worker fictício envia dois itens, limite e request-id persistem; subprocesso concorrente recusado com WORKER_BUSY/6.
Aceitação: AC-09 (worker), AC-20 e AC-16 (status sem corpo).
Decisões: comandos públicos run/resume/test serão expostos somente com adaptador SMTP funcional em T11/T12; transporte simulado fica nos testes. Histórico da execução deriva de attempts; contagens atuais usam vínculo de messages.
Próximo passo: T08, controles persistentes com relógio controlável.

Tarefa: T08
Estado: concluida
Alterações: checkpoints, pausa/SIGINT cooperativos, resume, intervalo global, janela 24h e retries no worker; Clock de testes e test_controls.py.
Verificação: uv run pytest -q — 26 passed; repetição dirigida da importação concorrente — 1 passed. Corrigidos encerramento ao atingir limites e disputa inicial de journal_mode.
Aceitação: AC-07, AC-08, AC-10, AC-19 e AC-15 (retry/orçamento; teste separado em T12). Pausa/reabertura preservam contadores; retry esgota cinco tentativas com esperas 1/5/15/60 minutos; limite de tentativas e duração mantém restante da fila.
Decisões: checkpoints a cada segundo fora da rede, jitter até 5s não negativo. SIGINT será também exercitado em subprocesso em T09.
Próximo passo: T09, encerrar processos nos marcos persistidos e resolver uncertain.

Tarefa: T09
Estado: concluida
Alterações: recuperação sob lock em worker.py, resolution.py, resolve na CLI, crash_driver.py e test_recovery.py.
Verificação: uv run pytest -q — 32 passed. Subprocessos encerrados em reserved/submission_started/após aceitação/após persistência; SIGINT cooperativo; falha de gravação de sucesso interrompe antes do próximo item; QUIT não desfaz sent.
Aceitação: AC-12, AC-13, AC-14, AC-18; complementa AC-08. Reenvio manual é novo registro pendente, vinculado e idempotente, com novo Message-ID; mark-sent registra origem manual.
Decisões: recuperação exige lock e resume explícito, aplica backoff também a interrupção segura; histórico original permanece.
Próximo passo: T10, setup local e backend Keychain explicitamente nativo com testes fictícios.

Tarefa: T10
Estado: concluida
Alterações: credentials.py, setup.py, setup na CLI e test_credentials.py. keyring==25.6.0 no projeto/lock, dependência já prevista no ADR-004.
Verificação: uv run pytest -q — 38 passed. Backend fictício, chaveiro bloqueado/negado/ausente, ausência de fallback, prompt exige TTY, captura de saída/arquivos sem segredo. Segredos fictícios são gerados em memória, nunca literais em testes.
Aceitação: AC-21. Keychain pessoal e conta real não acessados.
Decisões: setup usa gravação atômica privada, copia assinaturas para diretório local e recusa troca de conta no mesmo diretório.
Próximo passo: T11, SMTP simulado por sessão e doctor sem envelope/DATA.

Tarefa: T11
Estado: concluida
Alterações: SMTPTransport/doctor, integração CLI run/resume/doctor, migração 002 resume_after e testes de sessão SMTP.
Verificação: uv run pytest -q — 50 passed. Sessões simulam STARTTLS/certificado/auth, MAIL/RCPT/DATA, 4xx/5xx/quota, desconexão e QUIT. Doctor não usa MAIL/RCPT/DATA. Regressão AC-12–14 com subprocessos mantida.
Aceitação: AC-11, AC-12–14. Nenhuma conexão ao SMTP pessoal.
Decisões: timeouts por fase, respostas SMTP não persistidas em texto bruto; suspensão global de conta por quota/throttling (migração 002). Referências oficiais Apple/Python/keyring verificadas na data da execução, registradas em architecture.md.
Limitações: integração real iCloud continua não verificada (T14).
Próximo passo: T12, cópia idempotente através do mesmo worker.

Tarefa: T12
Estado: concluida
Alterações: testing.py, test na CLI, migração 003 de alvo da execução, test_test_copy.py e contratos correspondentes.
Verificação: uv run pytest -q — 55 passed. Destinatário de teste exclusivo no envelope/To, novo Message-ID, original inalterado, chave repetida/conflitante, 4xx/5xx/uncertain com apenas uma tentativa e orçamento compartilhado.
Aceitação: AC-06 e AC-15 completo (testes/retries/uncertain contabilizados). Nenhum envio real.
Decisões: cópia e execução atômicas, teste usa worker de uma tentativa; prefixo __test__: reservado. Cópias retry_wait não são recolhidas por execuções normais.
Próximo passo: T13, fluxo completo de CLI, revisão de contratos e instalação limpa.

Tarefa: T13
Estado: concluida
Alterações: test_end_to_end.py/cli_driver.py, test_regressions.py; validação completa de config/diretórios; migração 004 de histórico manual; suspensão/falha atômicas; retry respeita limite de mensagens distintas; requisitos/README/contratos/plano/aceitação; examples fictícios; requirements.lock e build-constraints.lock exportados de uv.lock.
Verificação: uv sync --locked --no-editable --reinstall-package send-mailqueue; uv run --no-sync pytest -q — 66 passed. uv build --build-constraints build-constraints.lock gerou wheel e sdist. Novo uv venv temporário com Python 3.13.14; uv pip install --require-hashes -r requirements.lock; wheel instalado --no-deps; dependências de testes exportadas do mesmo lock e instaladas com hashes; python -m pytest -q tests nesse ambiente — 66 passed. mailqueue --help e backup de banco vazio funcionaram no ambiente limpo; import do pacote confirmado em site-packages. Archives inspecionados: quatro migrações SQL incluídas; nenhum banco/log/pyc/.venv.
Aceitação: AC-01 a AC-21 demonstrados automaticamente; fluxo CLI real em subprocessos com sessão SMTP/credencial/relógio simulados: validate/import → preview HTML/EML → doctor → test → run → pausa durante DATA → status → resume → run idempotente → export → backup. Backend pessoal não acessado.
Decisões: migração 004 preserva decisões anteriores; suspensão da conta é atômica com a tentativa; diretórios locais e destinos de saída verificados. Instalação não editável resolve arquivos .pth marcados hidden neste ambiente. Grupo build fixa também transitivas do backend; não há nova dependência de produção além de keyring já prevista.
Limitações: preview visual no navegador não concluído devido à política file:; HTML restritivo testado. Remetente/iCloud e aparência recebida não verificados. Projeto não possui repositório Git inicializado; nenhum commit criado. Simulação pública não foi adicionada.
Próximo passo: somente T14, após pré-condições e autorização separada; não executar SMTP real sob a autorização de desenvolvimento.

Tarefa: T14
Estado: bloqueada
Alterações: nenhuma configuração pessoal ou envio real realizado; estado fiel registrado.
Verificação: pré-condições indisponíveis nesta conversa. O usuário autorizou desenvolvimento com envios simulados, não forneceu conta configurada/endereço para teste real nem autorização para essa cópia.
Aceitação: AC-22 não executado. Resultados simulados de T01–T13 não são evidência do teste real.
Decisões: manter comandos reais implementados, sem invocá-los contra conta pessoal durante desenvolvimento.
Próximo passo: usuário executa setup no terminal local (sem senha no chat); fornece endereço e autoriza explicitamente uma única cópia. Então executar doctor, preview e test com chave estável e confirmar com o usuário remetente/HTML/assinatura/cabeçalhos no recebido. Guardar somente resultado técnico sem credenciais/corpo pessoal no registro.

## Ajuste solicitado — setup mínimo e assinatura posterior

Estado: concluida.
Alterações: setup solicita apenas e-mail e senha de aplicativo; remetente inicial igual ao login; assinatura vazia. Repetição preserva preferências e --sender permite endereço autorizado opcional. Novo comando signature configura/remove assinatura sem pedir senha, com publicação atômica do par HTML/texto e efeito apenas em futuras importações. Documentação atualizada (ADR-007 e AC-23).
Verificação: uv sync --locked --no-editable --reinstall-package send-mailqueue; .venv/bin/python -m pytest -q — 69 passed. Ajuda dos comandos setup/signature conferida na instalação atualizada. Testes verificam preservação de preferências, importação congelada, remoção e ausência de senha em arquivos/saídas.
Próximo passo: usuário executa setup local com e-mail e senha de aplicativo. T14 continua pendente; nenhum e-mail real enviado neste ajuste.

## T14 — Teste real após configuração local

Estado: bloqueada apenas pela confirmação do recebimento/aparência pelo usuário.
Verificação: doctor retornou banco e Keychain OK, TLS verificado e autenticação OK. Preview HTML gerado. Uma única cópia de teste ao endereço indicado pelo usuário foi aceita pelo iCloud (SMTP 250), em uma tentativa, com estado sent e confirmation_source=smtp. Sem assinatura e com remetente iCloud conforme setup simplificado; domínio próprio e assinatura personalizada não foram exercitados.
O item original usado para gerar a cópia foi cancelado para não permanecer elegível a envio posterior. Nenhuma credencial ou corpo pessoal registrado aqui.
Próximo passo: confirmar recebimento e aparência com o usuário. Aceitação SMTP não comprova entrega na caixa de entrada.

## Ajuste — remetente padrão e nomes por mensagem

Estado: concluida. Novo comando sender altera endereço/nome sem pedir credencial. Lotes JSON/CSV aceitam sender_name e to_name; MIME congela nomes e envelope SMTP mantém endereços simples. Cópias de teste substituem o destinatário sem herdar o nome original; reenvio preserva nomes.
Verificação: instalação atualizada via uv sync; .venv/bin/python -m pytest -q — 74 passed. Configuração local aplicada e relida; composição MIME local confirmou o nome/endereço solicitado e login preservado. Nenhum novo envio realizado. AC-24 documentado.
A imagem enviada pelo usuário confirmou recebimento e HTML do teste anterior. O novo remetente de domínio próprio ainda precisa ser validado em envio autorizado; não declarar essa integração confirmada pelo teste anterior com endereço iCloud.

## T14 — Envio autorizado com domínio próprio

Uma cópia de teste usando o remetente de domínio próprio e nome configurados foi aceita pelo iCloud: SMTP 250, uma tentativa, estado sent. O item original foi cancelado para não permanecer pendente. Falta confirmação pelo usuário do recebimento e do nome/endereço exibidos; aceitação SMTP não comprova esses detalhes. Sem assinatura personalizada neste teste.

## T14 — Confirmação do recebimento

Estado: concluida. As imagens fornecidas pelo usuário mostram a mensagem recebida, HTML legível, nome e endereço do remetente de domínio próprio corretos. Aceitação SMTP 250 já registrada em uma única tentativa. AC-22 concluído para a configuração atual sem assinatura personalizada. Cabeçalhos técnicos de autenticação SPF/DKIM/DMARC não foram apresentados nem verificados. Não houve novo envio nesta confirmação.

## Ajuste — remover teto diário e variar intervalos

Estado: concluida. Teto local diário removido; configurações daily_budget antigas são ignoradas. Novas configurações usam intervalo de 15–45 segundos, sorteado por tentativa e persistido em attempts.delay_seconds (migração 005), contado após seu término. Pausa/reabertura preservam a espera. Limites por execução e throttling do provedor continuam ativos. Configuração local atualizada sem envio.
Verificação: suite completa — 76 passed; teste adicional de migração/cooldown e módulo storage — 4 passed. Cobertura inclui 101 mensagens simuladas em um dia, intervalos distintos persistidos entre execuções, compatibilidade com quota legada, preservação de cooldown do provedor e remoção de cooldown local antigo. AC-25 e ADR-009 documentados. Nenhuma mensagem real enviada.

## Ajuste — SMTP KingHost e nova conta

Implementação concluída; ativação local pendente da senha da nova caixa. Perfil kinghost usa SMTP_SSL em smtp.kinghost.net:465 com verificação de certificado. Setup recebe provedor/login/nome e --replace-account, captura somente senha no Terminal e preserva histórico/assinatura. Configuração legada continua iCloud até execução do setup da nova conta. Nenhuma credencial iCloud reaproveitada nem envio efetuado.
Verificação: instalação atualizada; .venv/bin/python -m pytest -q — 80 passed. AC-26 cobre TLS implícito/erro de certificado, doctor sem envio, troca explícita de conta e isolamento da fila antiga.
Próximo passo: usuário executa setup KingHost local; depois doctor. Envio real exige autorização específica. A verificação anterior T14 iCloud não valida KingHost.

## Correção — prompt de senha por provedor

Concluída: removida a menção genérica ao iCloud no prompt KingHost. Setup mostra provedor/login antes da captura sem eco. Reinstalação aplicada; 82 testes passaram, incluindo prompt específico de cada provedor. Nenhuma credencial acessada nem envio realizado nesta correção.

## KingHost — diagnóstico real após setup do usuário

Configuração local concluída pelo usuário. Doctor real retornou banco OK, Keychain OK, TLS verificado e autenticação OK em smtp.kinghost.net:465. Nenhum e-mail enviado neste diagnóstico. Próximo passo: cópia de teste real mediante autorização; a entrega KingHost ainda não foi verificada.

## KingHost — tentativa real autorizada e impedimento DNS

Teste real executado com uma única tentativa: autenticação e MAIL FROM aceitos, RCPT recusado com SMTP 450 / 4.1.8 / Sender address rejected: Domain not found. Nenhum DATA transmitido; nenhuma mensagem aceita. Diagnóstico adicional limitado ao envelope confirmou o motivo e encerrou com RSET, sem conteúdo. DNS MX e SOA do domínio do remetente retornaram SERVFAIL, com indicação de REFUSED no servidor autoritativo.
O original foi cancelado; a cópia de teste permanece no histórico, com execução esgotada e sem reenvio automático. Integração KingHost ainda bloqueada para entrega: corrigir DNS/delegação do domínio antes de novo teste. Nenhuma alteração de DNS foi feita.

## KingHost — DNS resolvido, impedimento TLS no novo teste

DNS público MX e SOA autoritativo agora respondem NOERROR. Novo teste autorizado interrompido antes da autenticação/transmissão: TLS_INVALID, nenhuma submissão reservada. Diagnóstico Python retorna verify_code=20, unable to get local issuer certificate. Conexões de inspeção mostraram certificados com emissores GlobalSign R46 e R6 distintos; LibreSSL validou uma cadeia R6, mas doctor Python repetido permaneceu TLS_INVALID. Causa precisa distinguir cadeia oferecida por backend e confiança local; nenhuma validação desabilitada nem certificado instalado. Mensagem não enviada; execução bloqueada, sem retry automático.

### Correção TLS KingHost — 2026-09-30

Concluída (REQ-08, AC-27, ADR-011). Bundle padrão do Python sem GlobalSign R46; certifi 2026.7.22 validou três conexões ao SMTP. Transporte agora usa autoridades do certifi, mantendo validação de hostname/cadeia e bloqueio antes da senha em falhas TLS. Dependência fixada, lock/export atualizados e CLI reinstalada. **84 testes passaram**. `mailqueue doctor --json` real retornou database=ok, keychain=ok, tls=verified, authentication=ok em smtp.kinghost.net:465, sent=false. Nenhum e-mail enviado nesta correção; entrega KingHost permanece pendente de teste real e confirmação do recebimento.

### Teste real KingHost após correção TLS — 2026-09-30

Usuário autorizou prosseguir. Um único teste enviado de remetente@example.com para destinatario@example.com, assunto “Teste KingHost — Raquel Talita”. Mensagem id-operacional-anonimizado: sent, uma tentativa, SMTP 250, phase=accepted, confirmation_source=smtp. Request-id kinghost-tls-fixed-test-2026-09-30-001. Execução terminou no limite explícito de uma mensagem. Aceitação SMTP confirmada; recebimento e aparência no cliente ainda aguardam confirmação do usuário.

### Recebimento KingHost e diagnóstico de spam — 2026-09-30

Usuário confirmou que o teste chegou ao spam. Consulta pública: SPF v=spf1 include:_spf.kinghost.net -all; _dmarc ausente (NXDOMAIN confirmado no DNS autoritativo dns1.kinghost.com.br). Isso não comprova causa da classificação. DKIM e resultados efetivos de SPF/DMARC aguardam cabeçalhos da mensagem recebida. Nenhum novo envio realizado.

### Cabeçalhos recebidos — diagnóstico KingHost, 2026-09-30

Mensagem de teste b50d2fa662204346937747d4c4f90380 confirmada no material do usuário. iCloud marcou JUNK/Junk, X-Suspected-Spam=true. SPF pass para 192.0.2.1 com envelope alinhado a example.com. Duas assinaturas KingHost rsa-sha1, d=dkim.kinghost.net, s=king1; ambas rejeitadas pelo iCloud com dkim=permerror (sha-1 unsupported). DMARC none. Defeito concreto na assinatura adicionada pelo provedor; cabeçalhos não revelam o peso exato no filtro nem comprovam que todos os envios KingHost são afetados. Próximo passo: solicitar ao provedor DKIM rsa-sha256, preferencialmente alinhado ao domínio, e publicar DMARC após conferir os emissores. Nenhum envio ou alteração DNS nesta análise.

### T15 — DKIM local (em andamento)

REQ-15 / AC-28 / ADR-012: implementar setup/status/enable/disable, chave nativa, assinatura e verificações; preparar registro DNS real. Ativação/envio aguardam publicação pelo usuário e verificação.

T15: implementação concluída; operação pendente do DNS. **92 testes passaram**, incluindo assinatura/verificação real com chaves efêmeras, adulteração de corpo/cabeçalhos, DNS ausente e chave incompatível, idempotência e bloqueio antes da rede. CLI instalada com dkimpy 1.1.8. Chave real criada no Keychain (sem arquivo privado); seletor seletor-exemplo, domínio example.com. Prova local com a chave real validada, sem envio. Configuração permanece pendente e bloqueia envios até dkim enable ou disable. Próximo passo: usuário publicar TXT público, verificar DNS, ativar e testar preservação da assinatura pela KingHost; recebimento autenticado ainda não comprovado.

T15 — DNS e teste real (2026-09-30): usuário confirmou publicação do TXT. `dkim enable` verificou assinatura contra DNS e ativou a configuração. Um único teste assinado aceito pela KingHost (SMTP 250), mensagem id-operacional-anonimizado, Message-ID message-id-anonimizado@example.com, request-id kinghost-local-dkim-test-2026-09-30-001. Uma tentativa, state=sent. Aguarda cabeçalhos recebidos para comprovar preservação da assinatura e dkim=pass no iCloud; classificação fora do spam ainda não comprovada.

T15 — concluída, confirmação de recebimento (2026-09-30). Usuário confirmou entrada fora do spam. Cabeçalhos da mensagem message-id-anonimizado@example.com confirmam dkim=pass para example.com (rsa-sha256, seletor seletor-exemplo), spf=pass, dmarc=pass e X-Apple-Action MOVE_TO_FOLDER/INBOX. KingHost preservou a assinatura local; sua assinatura rsa-sha1 continua permerror. IP de saída neste teste 192.0.2.1 difere do teste anterior (.68); não atribuir causalidade exclusiva à assinatura nem garantir inbox futuro. REQ-15 / AC-28 verificados em teste real, além dos 92 testes automatizados. Nenhum novo envio nesta confirmação.

### Assinatura HTML com imagens hospedadas — 2026-09-30

REQ-03 / REQ-06 / AC-04 / AC-06 / AC-22. Assinatura aprovada configurada por CLI em HTML e texto para futuras importações, com cinco imagens HTTPS no Supabase. Prévia MIME conferida: destinatário e remetente corretos, assinatura única, cinco URLs públicas e ausência de CID/base64. Usuário autorizou explicitamente um teste para sua caixa iCloud; uma única cópia foi aceita pela KingHost (SMTP 250), state=sent, phase=accepted, confirmation_source=smtp, uma tentativa. Registro original usado como modelo cancelado para não deixar duplicata pendente. Recebimento e aparência da assinatura no cliente aguardam confirmação do usuário; não confundir aceitação SMTP com entrega. Nenhuma alteração de código.

### Correção visual da assinatura — 2026-09-30

REQ-03 / AC-04 / AC-22. Imagem enviada pelo usuário confirma recebimento do teste anterior, mas mostra nome mais fino e ausência do traço dourado. V2 corrige nome e linha, preservando o retrato/monograma byte a byte e sua URL. Novo wordmark publicado com nome distinto; cinco imagens verificadas sem login (HTTP 200 e hashes iguais aos arquivos locais). Assinatura HTML/texto configurada pela CLI e conferida por leitura. Nenhum novo envio nesta revisão; aparência da v2 no cliente permanece pendente.

Teste real da assinatura v2 — 2026-09-30 (REQ-03,06 / AC-06,22): novo envio explicitamente autorizado; uma cópia da assinatura corrigida aceita pelo SMTP KingHost com código 250, state=sent, confirmation_source=smtp e uma tentativa. Assunto: “Teste de assinatura corrigida — Raquel Talita”. Modelo original cancelado após envio. Recebimento e aparência desta revisão aguardam confirmação do usuário.

## T16 — Arquivo IMAP KingHost (REQ-16 / AC-29 / ADR-013)

Estado: concluida. Migração 006, pedido atômico junto de sent, bytes SMTP preservados, IMAP separado e retry/reconciliação sem reenvio. Verificação: PYTHONPATH=src .venv/bin/python -B -m pytest -q — 113 testes (21 novos cenários IMAP) passaram após atualizar expectativa do número de migrações. Testes incluem quatro quedas de subprocesso, rejeição/desconexão, retry sem SMTP, comparação exata de Message-ID, cópias múltiplas, rollback atômico, migração/histórico, TLS antes do Keychain e bytes de transporte. CLI reinstalada com uv sync --locked --offline --no-editable --reinstall-package send-mailqueue; suíte da instalação: 113 passed. DKIM RSA-SHA256 válido preservado no arquivo com chave efêmera e SMTP/IMAP simulados. Configuração real concluída em T17.

## T17 — Configuração real IMAP sem envio (AC-30)

Estado: concluida; depende de T16. TLS e autenticação preliminares passaram pelo Keychain. LIST real encontrou apenas INBOX e INBOX.Spam; NAMESPACE INBOX. com delimitador ponto, sem \Sent. Escolha da pasta solicitada ao usuário; nenhuma pasta presumida. Não houve SMTP nem APPEND.

## T18 — Primeiro arquivo real

Estado: concluida. Após a configuração, usuário autorizou explicitamente nesta conversa um único teste para seu iCloud. Essa nova autorização permitiu o teste real; não autorizou a fila de prospecção. Arquivo conferido por leitura IMAP, sem depender de simulação. Exibição visual nos clientes e recebimento no iCloud ainda aguardam confirmação do usuário.

T17: usuário escolheu explicitamente criar INBOX.Sent e usá-la como Enviados. Hash antes da migração de todas as 128 mensagens: f8288e3394919f5ec9d09a58fc9ea00b306ea6ff7767fd8abd272a2f58aa0a05. Lote solicitado tem 114 pending e uma cópia histórica sent. Igualdade confirmada após migração 006/ativação: todos os 128 registros idênticos, 114 pending preservadas, archives vazia e integrity_check=ok.

T17 — evidência final (2026-09-30): `.venv/bin/mailqueue archive configure --folder INBOX.Sent --create --json` criou e subscreveu a pasta escolhida. `archive check --json` retornou enabled=true, tls=verified, authentication=ok, folder=INBOX.Sent, uidvalidity=1790778297 e appended=false em imap.kinghost.net:993. Keychain nativo existente, sem nova senha. Migração aplicada pela Store sob lock; hash e contagens preservados. Nenhuma mensagem enviada, nenhum APPEND, nenhum histórico arquivado. Próximo envio pela CLI atualizada já solicitará cópia, mas permissão/aceitação real de APPEND e exibição como pasta especial Enviados nos clientes aguardam T18. No Mail/webmail, usar a pasta Sent recém-criada como destino de enviados; preferências dos clientes não foram alteradas. Próximo passo exato: retomar somente na conversa original com autorização do envio; depois conferir `show ID`/`archive status ID` e presença em INBOX.Sent, sem repetir SMTP por falha de arquivo.

T18 — teste real autorizado (2026-09-30): uma cópia do lote enviada a destinatario@example.com, assunto “Cinco peças, quantos looks?”, pela CLI `test` com chave kinghost-imap-sent-test-2026-09-30-001. Mensagem id-operacional-anonimizado, Message-ID <message-id-anonimizado@example.com>, execução id-operacional-anonimizado. SMTP 250, uma tentativa, state=sent, confirmation_source=smtp. APPEND real aceito: archive.state=archived, INBOX.Sent, uma tentativa. Leitura independente por UID SEARCH e FETCH BODY.PEEK[] encontrou uma única cópia, UID 1, UIDVALIDITY 1790778297, bytes exatamente iguais ao wire_bytes persistido; From/To/Subject/Message-ID, MIME/corpo/assinatura preservados. DKIM local rsa-sha256 validou contra registro público configurado, sem acesso ao inbox iCloud.

As 114 mensagens pendentes mantiveram todas as colunas/bytes: hash antes/depois ce347c209091c19613c2d13f9f482ea7f5cf05e084bd5915da031b9df6bc0dd6. Nenhum histórico arquivado e nenhuma mensagem de prospecção enviada. Próximo passo: usuário conferir recebimento no iCloud e apresentação de Sent/Enviados no webmail/Mail; fila só será retomada na conversa original com autorização. Não repetir SMTP caso falhe somente o arquivo.


T18 — confirmação final do usuário (2026-09-30): usuário confirmou recebimento, envio e arquivamento correto na pasta Enviados. AC-31 concluído também na verificação visual. Autorização explícita recebida nesta conversa para enviar as 114 mensagens pendentes, sem novos testes, preservando conteúdo, idempotência, intervalos e limites. Consulta pela CLI confirmou 114 mensagens normais pending, sem execução vinculada; duas cópias históricas de teste permanecem fora do envio.

### Alternativa de assinatura sem foto — 2026-09-30

REQ-03 / AC-04. Usuário rejeitou o conjunto foto/RT e informou tê-lo apagado do servidor. V3 remove retrato, monograma e coluna lateral; preserva nome encorpado, subtítulo, contatos e redes sociais com traço dourado. HTML conferido sem referência ao ativo removido; quatro imagens HTTPS verificadas por HTTP 200 e igualdade de bytes. Configuração aplicada pela CLI apenas para futuras importações e confirmada por leitura. Nenhum envio, republicação do retrato ou alteração de mensagens já compostas. Prévia e pacote em exports/assinatura-raquel-talita-v3; visual em cliente real aguarda confirmação.

Operação autorizada — 2026-09-30 (em andamento): lote de 114 mensagens normais iniciado pela CLI atualizada; limites explícitos de 114 mensagens, 570 tentativas e 14400 segundos ativos, intervalos existentes preservados. Após 127 tentativas: 112 aceitações SMTP, todas com cópia IMAP arquivada após recuperar quatro falhas de conexão por archive retry; uma mensagem esgotou cinco tentativas e uma aguarda a quinta tentativa. Pausa cooperativa usada somente para recuperar arquivos, seguida de resume da mesma execução, sem renovar limites nem modificar conteúdo. Nenhum teste/histórico arquivado ou reenviado. Resultado final ainda pendente; dados operacionais permanecem no banco externo ao repositório.

Operação autorizada — resultado final (2026-09-30): execução concluída pela CLI (state=completed), 114 mensagens normais tentadas, 128 tentativas SMTP totais. 112 sent com confirmation_source=smtp e 112 cópias archived em INBOX.Sent; 2 failed após cinco tentativas por mensagem, 0 pending/retry_wait/sending/uncertain. Quatro falhas iniciais de conexão IMAP foram recuperadas exclusivamente por archive retry, com reconciliação pelo Message-ID e sem reenvio SMTP. Nenhum histórico ou teste antigo arquivado; conteúdo e identidades preservados. CLI retornou RUN_ATTENTION/saída 5 devido às duas falhas, e não por execução ainda aberta. Aceitação SMTP não comprova entrega na caixa de entrada. Não foram executados novos testes ou alterações de código nesta operação.

### T19 — Contrato de fila ensinado ao Gepeto (2026-10-06)

Estado: concluída quanto à atualização das instruções. REQ-01 a REQ-06 / AC-01 a AC-06. Plugin pessoal privado Gepeto atualizado de 1.0.3 para 1.0.4 via Plugin Creator, preservando identidade, audiência, configurações e todos os 31 arquivos existentes. Nova skill mailqueue-handoff ensina JSON v1, destinatário/assunto/HTML/texto, nomes opcionais, remetente configurado fora do lote, assinatura local, IDs estáveis e autorização separada para envio. As duas cópias de Skillmaster roteiam pedidos de fila para essa skill. Modelo fictício aceito por load_batch; campo from extra recusado. Onze testes existentes de importação, nomes e assinatura passaram. Leitura posterior confirmou o conteúdo dos seis arquivos publicados, descontando normalização de JSON e newline final pelo editor, na release pluginrel_6ac56648b6588191b4d359d42dfdb5df. Nenhuma fila real importada e nenhum e-mail enviado. Aplicação comportamental pela nova versão em outra sessão do Gepeto não verificada; código e contrato da CLI permanecem os existentes.

### Validação do pacote de beleza e teste da assinatura — 2026-10-08

REQ-02,03,05,06 / AC-02,03,04,06,22. Pacote externo validado pela CLI: 197 mensagens, 171 endereços, 137 marcas, would_create=197, reused=0, created=0. JSON e revisão HTML coincidem; composição em memória confirmou MIME e assinatura única nas 197 mensagens. Sem importação ou envio do lote de beleza. Ressalvas: seis caixas compartilhadas receberiam múltiplas mensagens (15/8/3/2/2/2) e 15 contatos incertos/históricos na revisão. Histórico consultado pela CLI não contém lote anterior de beleza nem destinatários coincidentes. Validação não comprova existência das caixas ou veracidade/atualidade das métricas.

Assinatura configurada coincide com a v3 sem foto/monograma. Quatro imagens públicas verificadas por HTTPS, HTTP 200 e hashes iguais aos ativos locais. Após autorização explícita do usuário nesta conversa, foi importado somente um modelo de teste e executada uma cópia para destinatario@example.com, de remetente@example.com, assunto “Validação da assinatura — Raquel Talita”. Request-id validacao-assinatura-raquel-2026-10-08-001; mensagem id-operacional-anonimizado; Message-ID <message-id-anonimizado@example.com>; execução id-operacional-anonimizado. Uma tentativa, SMTP 250/accepted, sent com confirmation_source=smtp; IMAP archived em INBOX.Sent, uma tentativa. Modelo id-operacional-anonimizado cancelado sem tentativa para não deixar envio adicional pendente. Nenhuma alteração de código.

Próximo passo: usuário confirmar recebimento e aparência da assinatura (nome, ícones e linha dourada). AC-22 para esta revisão visual permanece pendente; aceitação SMTP/arquivo não substituem essa confirmação. Resolver as ressalvas do pacote antes de uma autorização específica para o envio aos contatos. Relatório e dados de revisão permanecem fora do repositório, em diretório temporário privado.

### Diagnóstico do teste no spam — 2026-10-08

Usuário informou recebimento na pasta spam. Leitura IMAP somente de Enviados, usando BODY.PEEK[] e Message-ID exato, encontrou uma cópia do teste de assinatura de 08/10. Cabeçalho DKIM-Signature contém a=rsa-sha256, d=example.com, s=seletor-exemplo; verificação criptográfica da cópia transmitida passou tanto contra DNS público atual quanto contra a chave pública configurada. TXT do seletor coincide com a configuração. SPF público: v=spf1 include:_spf.kinghost.net -all; DMARC público: v=DMARC1; p=none. Isso confirma assinatura na origem e configuração DNS, sem comprovar os resultados calculados pelo iCloud ou a preservação após processamento da KingHost. A cópia de Enviados não contém Authentication-Results do destinatário. Próximo passo: obter os cabeçalhos completos ou EML da mensagem recebida no iCloud, para conferir DKIM/SPF/DMARC e IP de saída. Nenhum novo envio ou alteração de configuração realizado. Aparência visual da assinatura ainda não confirmada.

### Cabeçalhos recebidos do teste de assinatura — 2026-10-08

Material fornecido pelo usuário corresponde ao Message-ID <message-id-anonimizado@example.com>. O iCloud confirmou dkim=pass para example.com, spf=pass e dmarc=pass. A assinatura local RSA-SHA256 foi preservada e validada no destinatário. KingHost acrescentou duas assinaturas rsa-sha1, d=dkim.kinghost.net, s=king1, ambas com dkim=permerror (sha-1 unsupported). Apesar da autenticação alinhada válida, iCloud marcou X-Suspected-Spam=true, X-Apple-Action=JUNK/Junk e X-Spam-Flag=yes. IP de saída 192.0.2.1, diferente do teste histórico que chegou ao inbox em 30/09 (.25). Cabeçalhos não revelam pesos do filtro nem comprovam que SHA-1 ou reputação do IP causaram a classificação. Próxima ação recomendada: KingHost corrigir assinaturas SHA-1 e investigar reputação/entregabilidade desse IP; não é necessário substituir a assinatura local válida. Nenhuma configuração alterada, mensagem reenviada ou contato com suporte realizado. Confirmação visual da assinatura ainda pendente.

### Preparação do Git e README — 2026-10-19

Solicitação explícita do usuário: inicializar Git, revisar dados sensíveis, criar repositório, commit, push e Page de README. Código funcional preservado. E-mail pessoal, domínio, seletor DKIM, IPs e identificadores de mensagens reais anonimizados na documentação; exemplos usam remetente fictício. Originais da documentação preservados somente em cópia local privada temporária fora do Git. Exports e ativos pessoais mantidos localmente e ignorados, assim como bancos, credenciais, builds e previews. Revisão dos 66 arquivos selecionados sem padrões de tokens, chaves privadas ou dados pessoais identificados. A busca por padrões não constitui garantia de ausência de todo dado sensível.

Git local configurado em main com e-mail noreply do GitHub. Repositório privado criado em https://github.com/lucasmef/send-mail. Page privada criada e conferida por leitura: https://chatgpt.com/space/page_bb5bfa417abc8191b65a8c498943fe8a. README corrigido para refletir as três dependências de produção e o resultado já confirmado do teste IMAP histórico. Ambiente de desenvolvimento reparado por reinstalação das dependências fixadas, sem alterar o lock: 113 testes simulados passaram em 4,34s. Nenhum SMTP/IMAP real executado. Commit inicial 4f10778 publicado; push de main concluído com upstream origin/main. Hash local e remoto idênticos e árvore limpa conferidos após o envio. Preparação concluída.
