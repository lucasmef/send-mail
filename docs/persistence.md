# Persistência, estados e recuperação

## Banco e diretório

Arquivo `queue.db` em `~/Library/Application Support/SendMail`. Usar SQLite em disco local, `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON` e `busy_timeout` limitado. Diretório com permissão `0700`, arquivos sensíveis com `0600`.

Não copiar apenas o arquivo principal enquanto o banco está ativo. `backup` usa a API do SQLite. Restaurar backup antigo pode omitir envios posteriores: restauração deve ficar bloqueada para envio até reconciliação, nunca retomar automaticamente uma cópia antiga.

## Modelo mínimo

Quatro tabelas de domínio (messages, attempts, runs e archives) e `schema_migrations` para evolução do schema:

### `messages`

- `id`: identificador interno imutável.
- `batch_id`, `external_id`, `account_id`: chave única conjunta.
- `input_hash`: hash dos campos de entrada canônicos; usado para comparar reimportação.
- `content_hash`: hash do conteúdo final incluindo remetente e assinatura congelada.
- `sender`, `recipient`, `subject`, `html`, `text`, `mime_bytes`, `message_id`.
- `kind`: `normal` ou `test`; `source_message_id` vincula teste ou reenvio à origem.
- `request_id`: único quando criado por teste/reenvio, com hash dos parâmetros da operação.
- `state`: `pending`, `sending`, `retry_wait`, `sent`, `failed`, `uncertain`, `cancelled`.
- `run_id`: execução à qual está atualmente vinculado, se houver.
- `attempt_count`, `next_attempt_at`, `last_error_code`.
- `created_at`, `updated_at`, `sent_at`.
- `confirmation_source`: `smtp` ou `manual`, quando aplicável.
- `resolution_action`, `resolution_reason`, `resolved_at`: decisão sobre resultado incerto.

Reimportação idêntica usa `input_hash`, não a assinatura atualmente instalada: atualizar a assinatura não deve recriar nem alterar mensagens antigas. `Message-ID` e MIME congelados são reaproveitados nos retries do mesmo registro.

### `attempts`

- `id`, `message_id`, `run_id`, `started_at`, `finished_at`.
- `phase`: `reserved`, `connected`, `authenticated`, `envelope_ready`, `submission_started`, `accepted`.
- `outcome`: sucesso, falha transitória, falha permanente ou incerto.
- `smtp_code`, resposta sanitizada e `error_code`; nunca transcrição SMTP completa.
- `submission_reserved_at`: marco persistente de início de submissão, sem cota diária.

`attempts` mantém todas as tentativas; sucesso posterior não apaga falhas anteriores. Registrar códigos próprios para erros locais e códigos SMTP separadamente.

### `runs`

- `id`, `request_id` único, hash dos parâmetros, `batch_id`.
- `state`: `running`, `paused`, `interrupted`, `blocked`, `completed`, `limit_reached`.
- `pause_requested`, `max_messages`, `max_attempts`, `max_active_seconds`.
- `messages_started`, `attempts_started`, `active_seconds`, `heartbeat_at`.
- `created_at`, `updated_at`, `finished_at`, `blocked_reason`.

Datas em UTC; apresentação no fuso local. Índices em estado/próxima tentativa, lote e horário da reserva de submissão. Usar restrições `UNIQUE`, `CHECK` e referências quando aplicáveis.

## Ciclo de envio

1. Obter bloqueio exclusivo do worker por diretório de dados, mantido durante toda a execução. Um lock de sistema operacional, não apenas presença de arquivo ou PID.
2. Em transação curta, verificar pausa/limites, reservar item elegível, criar tentativa e persistir contadores.
3. Conectar, exigir TLS, autenticar e negociar envelope fora da transação.
4. Antes de transmitir conteúdo, persistir `submission_started` e seu horário. Se a gravação falhar, não transmitir.
5. Transmitir os bytes MIME congelados e esperar a resposta final.
6. Resposta positiva: gravar `sent` e tentativa aceita em transação. Se a gravação falhar, interromper o worker; não iniciar outra mensagem.
7. Resposta negativa explícita: classificar e persistir. Desconexão sem resposta conclusiva após o passo 4: `uncertain`.

Registrar `submission_started` antes da transmissão pode classificar como incerto algo que não chegou a ser transmitido. Essa escolha conservadora é intencional para evitar duplicidade.

## Erros e retries

- Falhas transitórias antes de transmissão e respostas SMTP 4xx explícitas permitem retry.
- Esperas: 1, 5, 15 e 60 minutos, com jitter pequeno; máximo de cinco tentativas totais por mensagem.
- Destinatário inválido/rejeição permanente: `failed`. Autenticação, remetente globalmente recusado ou TLS inválido bloqueiam a execução.
- Indicação de quota/throttling deve suspender novas submissões da conta; persistir o motivo e exigir retomada depois da espera ou correção. Não disparar retries em cada destinatário.
- Falha de `QUIT` depois de sucesso persistido não transforma o envio em falha.
- Timeout deve respeitar a fase SMTP; esperar a resposta final com tolerância adequada, evitando provocar resultados incertos por timeout excessivamente curto.

## Retomada e concorrência

Sob o lock exclusivo, reconciliar execuções antigas e tentativas incompletas. Heartbeat sozinho não autoriza tomar um worker ainda ativo.

- `sent`, `failed`, `cancelled`, `uncertain`: não elegíveis para retry automático.
- `pending`: elegível.
- `retry_wait`: elegível quando `next_attempt_at` chegar.
- `sending` sem `submission_started`: retry seguro, respeitando o total de tentativas.
- `sending` com `submission_started` sem resultado final persistido: `uncertain`.

`resume` preserva parâmetros e contadores. Nova execução pode recolher itens pendentes de uma execução encerrada, mas não itens de outra execução ainda ativa/pausada/interrompida. Contagens históricas por execução vêm das tentativas, não apenas do vínculo atual da mensagem.

Não há transação distribuída entre SQLite e SMTP. Uma aceitação seguida de queda antes da gravação local permanece incerta; `Message-ID` não oferece deduplicação garantida no servidor.

Implementação T02: migrações SQL numeradas são distribuídas dentro do pacote. `schema_migrations.sending_blocked` marca backups pela API; o worker recusa essas cópias. Não há comando de restauração/desbloqueio na v1. Backups exigem caminho ainda inexistente.

T08: checkpoints de tempo ativo e espera cooperativa ocorrem a cada segundo, além dos limites de cada operação. A espera global usa finished_at (ou started_at se ainda ausente) mais delay_seconds persistido. Retry usa jitter não negativo de até cinco segundos.

Migração 002: runs.resume_after persiste suspensão da conta. Throttling explícito aplica espera mínima de 1h e retomada explícita. Uma nova execução também respeita suspensão vigente do diretório (uma conta).

Migração 003: runs.test_message_id seleciona exclusivamente a cópia de teste no mesmo worker. Execução de teste tem limite de uma tentativa; retry_wait resultante nunca é recolhido por execução normal. Cópia e execução são criadas na mesma transação.

Migração 004: messages.resolution_history_json guarda todas as decisões manuais em ordem, sem apagar motivos anteriores. show/export expõem resolution_history como array; campos resolution_* indicam a decisão mais recente. Suspensão de conta e falha de tentativa são gravadas na mesma transação.

Migração 005: attempts.delay_seconds persiste a espera sorteada entre 15 e 45 segundos por tentativa. Registros anteriores recebem 15 segundos. Remover somente cooldowns antigos originados pela cota diária local, preservando throttling do provedor e cooldowns derivados dele. Não reiniciar execuções automaticamente. submission_reserved_at permanece para recuperação/auditoria.

## Migração 006 — archives

Tabela vinculada por archives.message_id ao ID local da mensagem, com state (pending/appending/archived/failed/uncertain), folder, wire_bytes, attempts, last_error_code, created_at, updated_at, archived_at, uid e uidvalidity. Sem inserir registros históricos e sem modificar messages. INSERT do pedido na mesma transação de sent/attempt accepted, somente quando arquivo está configurado. Pasta e bytes ficam congelados nesse pedido. Nenhuma transação aberta em rede. Queda em pending permite busca e APPEND; queda em appending exige reconciliação, nunca APPEND por mera ausência. uid é registrado quando reconciliado; APPENDUID é opcional. Backup preserva pedidos/bytes e também bloqueia retry de arquivo.
