# Send Mail

CLI local para macOS e Python 3.13: importa e revisa e-mails, mantém fila em SQLite e envia por SMTP do iCloud ou KingHost com TLS e senha nas Chaves.

**T01–T18 concluídas. SMTP KingHost com DKIM local e primeiro arquivo IMAP real verificados. Uma cópia em INBOX.Sent foi conferida por leitura, com bytes iguais aos transmitidos. 113 testes automatizados passaram; usuário confirmou recebimento e arquivamento correto na pasta Enviados.**

## Instalação e desenvolvimento

Instale `uv` pelo distribuidor oficial e execute na pasta do projeto:

```sh
uv sync --locked --no-editable
uv run --no-sync mailqueue --help
uv run --no-sync pytest -q
```

O lock fixa dependências diretas e transitivas; `.python-version` fixa Python 3.13.14. As dependências diretas de produção são `keyring`, `certifi` e `dkimpy`. A instalação não editável funciona também em ambientes que marcam arquivos `.pth` como ocultos no macOS. Depois de modificar código, reinstale antes de testar:

```sh
uv sync --locked --no-editable --reinstall-package send-mailqueue
uv run --no-sync pytest -q
```

Para construir e instalar a ferramenta fora do checkout:

```sh
uv export --locked --no-dev --no-emit-project --output-file requirements.lock --quiet
uv export --locked --only-group build --no-emit-project --output-file build-constraints.lock --quiet
uv build --build-constraints build-constraints.lock
uv tool install --python 3.13.14 --constraints requirements.lock dist/send_mailqueue-0.1.0-py3-none-any.whl
mailqueue --help
```

Ao atualizar, revise o código/lock, gere um backup com o worker parado, sincronize/reconstrua e reinstale a nova versão com as constraints correspondentes (`uv tool install --force ...`). O banco evolui por migrações numeradas; não apague `queue.db`. A versão do pacote desta entrega é 0.1.0.

## Configuração local

Execute `mailqueue setup` em um terminal local. Ele pede **somente e-mail iCloud e senha específica de aplicativo**, sem eco. O remetente inicial é o mesmo e-mail e a assinatura começa vazia. Não forneça senha no chat. Repetir setup preserva assinatura, limites e remetente existentes.

Para começar neste checkout:

```sh
.venv/bin/mailqueue setup
```

Depois, forneça à IA destinatário, assunto e texto do e-mail; ela prepara a importação. Não é preciso configurar assinatura para enviar.

A assinatura pode ser configurada ou removida depois, sem informar a senha novamente:

```sh
mailqueue signature --html /caminho/assinatura.html
mailqueue signature --clear
```

O texto simples é gerado automaticamente; `--text /caminho/assinatura.txt` permite personalizá-lo. A alteração vale apenas para futuras importações. Para usar um remetente de domínio próprio autorizado, há a opção `mailqueue setup --sender voce@seu-dominio.com`.

Padrão: `~/Library/Application Support/SendMail`, com diretório `0700` e arquivos privados `0600`. `--data-dir` aceita outro diretório local; use fora do repositório e de pastas sincronizadas. O programa recusa caminhos de sincronização conhecidos, mas você precisa escolher armazenamento realmente local.

`mailqueue doctor --json` verifica banco, configuração, Chaves, TLS e autenticação sem negociar destinatário nem enviar conteúdo. Ele acessa a conta real quando executado normalmente; não o executamos contra sua conta durante desenvolvimento.

## Operação por IA

Prepare um lote com IDs estáveis conforme [docs/cli.md](docs/cli.md); [examples/batch.json](examples/batch.json) e as assinaturas em `examples/` são fictícios. O importador não interpreta instruções nem executa templates.

```sh
mailqueue validate lote.json --json
mailqueue import lote.json --json
mailqueue list --batch meu-lote --limit 20 --json
mailqueue show m_ID --json
mailqueue preview m_ID --format html --json
mailqueue preview m_ID --format eml --json
```

Os IDs reais vêm do JSON de resposta. `show --include-body` solicita o corpo explicitamente. Preview retorna caminho absoluto e não abre aplicativos. HTML preserva texto/formatação básica; remove CSS, imagens, formulários, scripts e frames. EML contém os bytes MIME congelados. A inspeção visual no navegador não pôde ser feita nesta execução porque a ferramenta bloqueou URLs `file:`.

Após autorização do usuário para o endereço e o escopo de envio:

```sh
mailqueue test m_ID --to endereco-autorizado@example.com --request-id teste-estavel --json
mailqueue run --batch meu-lote --limit 20 --max-attempts 40 --max-seconds 1800 --request-id execucao-estavel --json
mailqueue status --run r_ID --json
mailqueue pause --run r_ID --json
mailqueue resume --run r_ID --json
```

**`test`, `run` e `resume` usam SMTP real na CLI instalada.** Transporte simulado existe apenas nos testes; não há flag pública de simulação. A instrução para desenvolver não autoriza esses comandos contra destinatários reais. AC-22 deve ser concluído antes da primeira operação com destinatários externos.

Uma chave repetida retorna o recurso existente; nunca gera outro worker/envio. Parâmetros conflitantes são recusados. Para continuar, use `resume`. Uma cópia de teste tem outro Message-ID, um destinatário explícito e no máximo uma tentativa; não modifica o original.

Default: uma conexão por tentativa, espera sorteada entre 15 e 45 segundos após cada tentativa e cinco tentativas totais por mensagem. Sem limite diário local. O intervalo sorteado fica no banco e vale também entre execuções e testes. Limites por execução e suspensões impostas pelo provedor continuam ativos. Pausa/Ctrl+C concluem a operação atual; retomada preserva limites e tempo ativo. Mac ligado, acordado e conectado é necessário. Não há serviço automático após reboot.

## Resultados e recuperação

`sent` comprova aceitação SMTP gravada, ou decisão manual identificada por `confirmation_source=manual`; não comprova entrega na caixa de entrada. Uma possível aceitação sem confirmação local vira `uncertain` e nunca é repetida automaticamente. `status` consulta sem corpo e não envia.

```sh
mailqueue cancel m_ID --json
mailqueue resolve m_ID --action mark-sent --reason "Recebimento confirmado pelo usuário" --json
mailqueue resolve m_ID --action cancel --reason "Usuário decidiu encerrar" --json
mailqueue resolve m_ID --action resend --reason "Usuário autorizou nova cópia" --request-id nova-copia-estavel --json
mailqueue export --batch meu-lote --output /caminho/local/exportacao.json --json
mailqueue backup --output /caminho/local/copia.db --json
```

`resend` apenas cria outra mensagem pendente vinculada; exige início explícito posterior. O histórico preserva motivos anteriores. `cancel` exige item ainda não submetido e sem tentativa em andamento. Exportação inclui corpos e histórico; cuide desses arquivos. Destinos devem estar fora do projeto/sincronização e ainda não existir.

Backup usa a API SQLite e pode ocorrer com atividade. **Backups são marcados como bloqueados para envio**: restaurar uma cópia antiga pode omitir envios posteriores. A v1 não tem comando de restauração/desbloqueio; reconciliação é necessária antes de usar uma cópia como fila. Nunca copie apenas `queue.db` com banco ativo. SQLite não criptografa conteúdo; proteção do Mac/backups continua necessária.

As operações respondem com um objeto JSON v1 em stdout; prompts/progresso vão para stderr sem segredos. Saídas: 0 sucesso, 2 entrada, 3 conflito, 4 configuração/autenticação/permissão, 5 atenção para falhas/incertos/orçamento, 6 worker ocupado. Consulte `error.code`; não repita automaticamente operações de envio com chave nova.

## Documentação e estado

- [AGENTS.md](AGENTS.md): regras do projeto.
- [TASKS.md](TASKS.md): andamento, verificações e próximo passo.
- [Especificação](docs/spec.md), [CLI](docs/cli.md), [persistência](docs/persistence.md), [arquitetura](docs/architecture.md).
- [Aceitação](docs/acceptance.md): cobertura automatizada e confirmação real de AC-22.
- [Plano](docs/implementation-plan.md): etapas verificadas.

Sem servidor web, frontend, ORM, broker, Docker, automação de Mail.app ou IA interna. O provedor externo fornece SMTP e, quando configurado, IMAP; se uma IA remota receber os textos na conversa, esses textos também passam pelo serviço dessa IA.

## Nome e endereço do remetente

Use `mailqueue sender --email contato@example.com --name "Nome da Equipe"` para definir o padrão sem digitar senha novamente. Login iCloud permanece separado. A IA pode informar `sender_name` e `to_name` em cada mensagem do lote para personalizar os nomes. Mudanças se aplicam a novas importações, preservando o histórico e o MIME já preparado.

## Trocar para KingHost

```sh
.venv/bin/mailqueue setup --provider kinghost --email contato@example.com --sender-name "Nome da Equipe" --replace-account
```

O comando pede apenas a senha da caixa de e-mail, grava nas Chaves e troca a conta ativa. Histórico e mensagens antigas são preservados e não entram na fila da nova conta. Perfil direto: smtp.kinghost.net:465, TLS implícito obrigatório. Senha iCloud não é reaproveitada. Depois use doctor para conferir autenticação sem enviar. Revenda/SMTP internacional podem exigir outro servidor: confirme o produto contratado antes de adaptar o perfil. A troca de provedor não confirma permissão para prospecção; aplicam-se os termos do serviço contratado.

Certificados TLS: a aplicação inclui o bundle de autoridades públicas do certifi para evitar dependência da lista antiga de certificados do Python/macOS. A validação permanece obrigatória. Atualizações do bundle são feitas junto das dependências da aplicação; não é necessário instalar certificados manualmente no Mac.

### Assinatura DKIM local opcional

Para assinar com RSA-SHA256 usando o próprio domínio:

1. Execute `mailqueue dkim setup --json`. A chave RSA 2048 fica somente no Keychain nativo; a saída contém o registro público TXT para o painel DNS.
2. Cadastre `host` e `value` no domínio indicado. Se o painel acrescenta o domínio, use apenas `host`. O valor longo deve formar um único registro TXT (o provedor pode dividi-lo internamente em trechos).
3. Execute `mailqueue dkim enable --json`. Só ativa após verificar uma assinatura contra o DNS publicado.
4. Faça um teste autorizado e confira `dkim=pass` com o domínio do remetente nos cabeçalhos recebidos.

`mailqueue dkim status --json` mostra os dados públicos. Enquanto a configuração estiver pendente, envios ficam bloqueados. `mailqueue dkim disable --json` remove essa configuração sem apagar a chave das Chaves; um setup posterior gera novo seletor. Mudança para outro domínio exige nova configuração. A chave não integra backups da fila: preservar o Keychain também é necessário para recuperação. DKIM cobre mensagens já importadas no momento de envio; o corpo e os cabeçalhos originais persistidos não são alterados. A assinatura de transporte não aparece no preview/EML anterior ao envio. `doctor` verifica SMTP, não substitui a verificação DKIM. A assinatura local pode coexistir com a da KingHost; não garante classificação fora do spam.

## Cópias em Enviados na KingHost

`mailqueue archive configure --json` descobre a pasta por indicação IMAP de enviados. Se a conta não indicar uma pasta única, escolha uma das retornadas com `--folder NOME`. Para criar uma pasta inexistente, informe também `--create`; configure webmail/Mail para usar essa mesma pasta. `archive check --json` verifica a configuração sem enviar nem arquivar.

Após ativação, próximas aceitações SMTP geram cópia dos bytes enviados via IMAP. Mensagens pendentes mantêm seu conteúdo; histórico/testes antigos não são arquivados. Falha de arquivo mantém sent e nunca reenvia SMTP. `archive status ID --json` consulta; `archive retry ID --json` tenta somente o arquivo pendente/falho ou reconcilia incertos. Se uma cópia possivelmente aceita não aparecer na busca por Message-ID, o estado permanece uncertain para evitar duplicação. `archive disable` desativa novos pedidos. Retomar SMTP não tenta arquivos históricos.

Verificação real registrada em 2026-09-30: uma cópia autorizada foi aceita pelo SMTP e arquivada em INBOX.Sent. Leitura IMAP confirmou um único Message-ID e bytes idênticos, com DKIM válido. O usuário confirmou recebimento e apresentação na pasta Enviados. Esses resultados históricos não garantem entregabilidade futura.

## Privacidade do repositório

O Git contém código, testes com transporte simulado, exemplos fictícios e documentação. Exports, imagens de assinaturas, builds, bancos, backups, previews, logs e arquivos de ambiente ficam ignorados. Senhas e chaves privadas permanecem no Keychain nativo do macOS.

Dados pessoais e identificadores operacionais nos registros históricos foram anonimizados antes do primeiro commit. Resultados e datas de verificações anteriores foram preservados; esta preparação do repositório não realiza novos envios.
