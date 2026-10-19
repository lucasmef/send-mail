# Contrato da CLI — v1

Nome: `mailqueue`. Interface implementada e verificada com transporte simulado; integração real confirmada em AC-22 para a configuração atual.

## Entrada de lote

```json
{
  "schema_version": 1,
  "batch_id": "comunicado-2026-09",
  "messages": [
    {
      "external_id": "contato-001",
      "to": "pessoa@example.com",
      "subject": "Atualização",
      "html": "<p>Olá! Segue a atualização combinada.</p>",
      "text": "Olá! Segue a atualização combinada."
    }
  ]
}
```

JSON aceita somente os campos documentados. CSV usa cabeçalho `external_id,to,subject,html,text`, UTF-8 e regras usuais de aspas; `text` pode estar vazio. CSV exige `--batch`. Nenhum dos formatos contém senha ou instruções de execução. Endereço do remetente vem da configuração local. JSON aceita `sender_name` e `to_name` opcionais por mensagem. CSV aceita essas colunas opcionais após as cinco colunas existentes; campos vazios usam o padrão. `sender_name` substitui o nome padrão, sem alterar login/endereço. Nomes são congelados no MIME e participam da idempotência quando informados no lote.

## Comandos

| Comando | Contrato |
|---|---|
| `mailqueue setup --provider kinghost --email EMAIL --sender-name NOME --replace-account` | Troca a conta ativa para KingHost, preservando histórico; pede apenas senha local. Remetente inicial igual ao novo login. |
| `mailqueue setup` | Solicita apenas e-mail e senha de aplicativo; remetente inicial igual ao login e assinatura vazia. Preserva preferências existentes; `--sender EMAIL` é opcional. |
| `mailqueue signature --html ARQUIVO [--text ARQUIVO]` | Configura assinatura sem pedir senha; texto simples automático quando omitido; vale para novas importações. |
| `mailqueue signature --clear` | Remove assinatura de futuras importações, sem alterar mensagens existentes. |
| `mailqueue sender --email EMAIL --name NOME` | Altera remetente/nome padrão sem pedir senha; qualquer uma das opções pode ser usada separadamente. Vale para novas importações. |
| `mailqueue doctor` | Verifica configuração, banco, Keychain, conexão, TLS e autenticação; não envia e-mail. |
| `mailqueue validate lote.json` | Valida entrada e conflitos com a fila sem gravar ou enviar. |
| `mailqueue import lote.json` | Valida, compõe e grava atomicamente; itens idênticos existentes são ignorados. |
| `mailqueue import lista.csv --batch LOTE` | Mesmo comportamento para CSV. |
| `mailqueue preview ID --format html` | Exporta preview protegido; retorna caminho absoluto. |
| `mailqueue preview ID --format eml` | Exporta bytes MIME; não envia nem abre aplicativos automaticamente. |
| `mailqueue test ID --to EMAIL --request-id CHAVE` | Cria cópia de teste com outro destinatário e Message-ID e executa uma única tentativa; não altera o item original. |
| `mailqueue run --batch LOTE --limit 20 --request-id CHAVE` | Cria execução idempotente e roda worker em primeiro plano. |
| `mailqueue run ... --max-attempts 40 --max-seconds 1800` | Sobrescreve limites da execução antes de começar. |
| `mailqueue status --run ID` | Retorna resumo da execução sem corpos de mensagens. |
| `mailqueue list --batch LOTE --state failed --limit 20` | Lista paginada; `--cursor` solicita página seguinte. |
| `mailqueue show ID` | Exibe metadados e tentativas; corpo somente com `--include-body`. |
| `mailqueue pause --run ID` | Persiste pedido de pausa e retorna imediatamente. |
| `mailqueue resume --run ID` | Recupera estado e roda worker com orçamento restante. |
| `mailqueue cancel ID` | Cancela item ainda não submetido e sem tentativa em andamento. |
| `mailqueue resolve ID --action mark-sent --reason TEXTO` | Resolve item incerto por decisão manual, identificada como tal no histórico. |
| `mailqueue resolve ID --action cancel --reason TEXTO` | Encerra item incerto sem novo envio. |
| `mailqueue resolve ID --action resend --reason TEXTO --request-id CHAVE` | Cria novo item pendente vinculado ao incerto; não envia imediatamente. |
| `mailqueue export --batch LOTE --output arquivo.json` | Exporta mensagens e histórico; nunca credenciais. |
| `mailqueue backup --output copia.db` | Backup consistente pela API do SQLite. |

Comandos operacionais aceitam `--json`. `setup` não recebe segredo por argumentos nem retorna segredo em JSON. `--data-dir` permite diretório isolado para testes; o padrão é `~/Library/Application Support/SendMail`.

`run` em primeiro plano não exige que uma chamada de IA fique bloqueada: o ambiente executor pode mantê-lo em uma sessão de processo e executar `status` separadamente. A CLI não promete sobreviver ao encerramento dessa sessão.

## Idempotência de comandos

- `request_id` é obrigatório em `run`, `test` e `resolve --action resend`.
- Repetição da mesma chave e mesmos parâmetros retorna o recurso existente, sem novo envio ou worker. Para continuar uma execução existente, usar `resume`.
- Mesma chave com parâmetros diferentes retorna `IDEMPOTENCY_CONFLICT`.
- `batch_id` e `external_id` são estáveis; não gerar novos IDs a cada retry da IA.

## Saída estruturada

```json
{
  "schema_version": 1,
  "ok": true,
  "data": {
    "run_id": "r_42",
    "state": "paused",
    "counts": {"sent": 18, "pending": 2, "failed": 0, "uncertain": 0}
  }
}
```

```json
{
  "schema_version": 1,
  "ok": false,
  "error": {
    "code": "IDEMPOTENCY_CONFLICT",
    "message": "Esta chave já existe com outro conteúdo.",
    "retryable": false
  }
}
```

`stdout` contém apenas um objeto JSON por comando ao terminar. Progresso humano opcional vai para `stderr`, sem corpos e segredos. `status` permite acompanhar execução longa; não há polling automático pela IA em intervalos curtos.

Códigos de saída: `0` operação concluída conforme o contrato; `2` entrada inválida; `3` conflito; `4` configuração/autenticação/permissão; `5` atenção necessária ou execução com falhas/incertos; `6` worker ocupado. `status` pode retornar `0` ao consultar com sucesso uma execução que contém erros; o estado fica no JSON.

Semântica de `sent`: aceitação SMTP registrada ou resolução manual explicitamente marcada por `confirmation_source`; nunca ocultar a diferença.

Preview aceita `--output CAMINHO`; o padrão usa um novo arquivo privado em `DATA_DIR/previews/`. Exportações e backup exigem destino inexistente. Datas JSON são segundos Unix UTC. Cursor de listagem é opaco e vinculado aos filtros; ordenação por criação/ID.

O prefixo de request-id `__test__:` é reservado internamente e não pode ser usado em run. Uma cópia de teste com falha segura pode ficar retry_wait, mas sua execução tem uma tentativa total e não é retomada para reenviar. Outra tentativa deliberada exige outra chave explícita.

Erros globais de autenticação/TLS/Keychain/remetente retornam código de saída 4; execuções com failed/uncertain ou bloqueio de orçamento retornam 5 com resumo em error.details. Resumos de status mostram contagens dos vínculos atuais e history/outcomes das tentativas históricas. Corpos aparecem apenas em show --include-body, export e arquivos de preview. Configuração inválida gera CONFIG_INVALID; operações de leitura podem criar/migrar o banco, mas nunca inserem mensagens ou enviam.

Não há limite diário local. A configuração aceita interval_min_seconds e interval_max_seconds (padrões 15 e 45). A espera é sorteada e persistida por tentativa. Os limites de mensagens, tentativas e duração da execução continuam ativos; para lotes maiores, ajustar --limit, --max-attempts e --max-seconds explicitamente. daily_budget legado é ignorado.

Setup mostra o provedor e login selecionados em stderr antes de capturar a senha. Para KingHost, o prompt pede exclusivamente a senha da caixa KingHost; a referência à senha de aplicativo aparece somente no perfil iCloud.

## DKIM local

`mailqueue dkim setup`: gera chave RSA 2048 no Keychain, publica configuração pendente e retorna TXT público; repetição retorna configuração existente sem substituir chave. Domínio inferido do remetente. `mailqueue dkim status`: mostra apenas dados públicos. `mailqueue dkim enable`: valida assinatura de prova contra DNS antes de ativar. `mailqueue dkim disable`: desativa sem apagar chave. Todos aceitam --json/--data-dir e nunca enviam. Falhas retornam DKIM_CONFIG_INVALID, DKIM_KEY_ERROR, DKIM_DNS_INVALID ou DKIM_SIGN_FAILED. Envio bloqueado retorna DKIM_NOT_ENABLED ou erro DKIM correspondente, sem DATA.

## Arquivo IMAP (REQ-16)

Todos aceitam --json/--data-dir e nunca enviam SMTP:

- `archive configure [--folder NOME [--create]]`: autentica, lista e seleciona somente leitura; salva pasta para futuras aceitações. Sem pasta disponível retorna needs_folder=true e enabled=false. --create cria/subscreve apenas a pasta explícita.
- `archive check`: verifica TLS, autenticação, LIST e EXAMINE da pasta configurada, sem APPEND. Retorna host, port, tls, authentication, folder, uidvalidity, folders, enabled, appended=false. Não prova permissão efetiva de APPEND nem integração visual no webmail/Mail.
- `archive disable`: desativa futuros pedidos; preserva os existentes.
- `archive status ID`: estado separado, ou not_requested para histórico sem pedido.
- `archive retry ID`: reconcilia e tenta apenas arquivo do pedido já existente, na conta ativa. Não cria pedidos para histórico. Se uncertain e busca vazia, conserva uncertain. Repetir archived é no-op.

show/export incluem archive; status --run inclui contagens archives sem corpos. Estado sent/resultado SMTP permanecem independentes. archive retry retorna saída 5/ARCHIVE_ATTENTION com estado em details quando não confirmado; erros estáveis incluem ARCHIVE_NOT_REQUESTED, ARCHIVE_ACCOUNT_CONFLICT, IMAP_FOLDER_UNAVAILABLE, IMAP_AUTH_FAILED, IMAP_TLS_INVALID, IMAP_PROTOCOL_FAILED, IMAP_CONNECTION_FAILED, IMAP_APPEND_REJECTED, IMAP_UNCERTAIN_NOT_FOUND e IMAP_DUPLICATES_FOUND. Falhas de Keychain mantêm códigos existentes. Nomes de pasta são os nomes IMAP ASCII/UTF-7 modificado da lista, sem conversão de apresentação.
