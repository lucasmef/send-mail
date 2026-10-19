# Decisões de arquitetura

## ADR-001 — CLI Python, sem servidor

Decisão: usar um pacote Python com comando `mailqueue`. IA prepara conteúdo e invoca operações determinísticas. Worker não chama modelos.

Motivo: uso esporádico em um Mac, volume baixo e necessidade de baixo consumo de tokens. Python oferece a maior parte dos componentes necessários na biblioteca padrão.

Instalação prevista: projeto com `pyproject.toml`, `.python-version` e `uv.lock`; ambiente de desenvolvimento sincronizado pelo lock. A instalação de release precisa fixar também dependências transitivas por constraints exportadas do lock, pois instalar uma ferramenta com `uv tool install` por si só não garante consumir o lock do projeto.

## ADR-002 — SQLite para estado, JSON para intercâmbio

Decisão: tabelas messages, attempts, runs e archives (acrescentada pela ADR-013), sem ORM. Não implementar banco por regravação de JSON.

Motivo: transações, concorrência, unicidade e recuperação são requisitos centrais. SQLite não exige serviço nem dependência Python externa.

## ADR-003 — SMTP direto

Decisão: `smtp.mail.me.com:587`, STARTTLS obrigatório com validação de hostname/certificado, autenticação após TLS. Login é o endereço iCloud completo; remetente é o endereço autorizado do domínio próprio.

Motivo: composição HTML/MIME previsível e acesso direto aos resultados SMTP. AppleScript aproveitaria a conta do Mail.app, mas adicionaria dependência da fila e limitações de composição do aplicativo.

O primeiro teste real valida o remetente na conta concreta. Não assumir que autenticação bem-sucedida prova permissão para qualquer endereço de origem.

## ADR-004 — Keychain

Decisão: `keyring` com backend nativo do macOS selecionado explicitamente. Sem fallback para arquivo, variável de ambiente ou argumento de CLI. Captura via prompt sem eco.

Motivo: configuração única e armazenamento administrado pelo sistema. Keychain bloqueado ou autorização negada impede envio e retorna erro útil.

Limite: scripts executados pelo mesmo interpretador autorizado podem acessar o segredo; isso não é isolamento contra código malicioso do mesmo usuário. Banco e backups contêm conteúdo de e-mails e não são criptografados pelo SQLite comum; FileVault e proteção dos backups são complementares.

## ADR-005 — Processo sob demanda e envio sequencial

Decisão: worker em primeiro plano, um por diretório, retomada explícita. Sem LaunchAgent inicialmente.

Motivo: evita instalação e manutenção de serviço. A IA pode usar uma sessão de processo do seu executor e consultar a CLI separadamente. Se a sessão morrer, a persistência permite continuar.

## ADR-006 — Preview sem conteúdo ativo

Decisão: gerar documento de preview com política de conteúdo restritiva: sem scripts, formulários, frames, navegação automática ou carregamento remoto automático. Links não são visitados pelo programa. Na v1 implementada, uma lista positiva preserva texto e formatação básica, mas remove todo CSS, imagens e mídia (inclusive locais), atributos de eventos e elementos ativos. CSP nega recursos, scripts, frames e formulários. A aparência é aproximada. Aplicar sanitização/escape apropriados ao invólucro de preview sem alterar os bytes MIME congelados.

Motivo: HTML recebido pela IA pode ser não confiável. Preview de navegador é aproximado; teste recebido é a verificação de aparência no cliente de e-mail.

## Estrutura prevista de implementação

```text
src/mailqueue/
  cli.py          # comandos e contrato JSON
  config.py       # config local e diretório de dados
  storage.py      # schema, transações e backups
  importer.py     # JSON/CSV e idempotência
  composer.py     # MIME, texto e assinatura
  worker.py       # fila, pausa, limites e recuperação
  transport.py    # SMTP e classificação de fase/resultado
  credentials.py  # Keychain
  preview.py      # HTML protegido e EML
migrations/
tests/
```

Os nomes são orientativos; preservar os contratos é mais importante que dividir código em muitos arquivos.

## Referências verificadas na fase de planejamento

- [Configuração SMTP do iCloud](https://support.apple.com/en-gb/102525).
- [Senhas específicas de aplicativo](https://support.apple.com/en-gb/102654).
- [Limites do iCloud](https://support.apple.com/en-ie/102198): 1.000 mensagens e 1.000 destinatários por dia publicados; não representam garantia de throughput. O serviço proíbe envio em massa não solicitado.
- [SMTP no Python](https://docs.python.org/3/library/smtplib.html).
- [Durabilidade no SQLite](https://www.sqlite.org/pragma.html#pragma_synchronous).
- [Segurança do keyring](https://keyring.readthedocs.io/en/latest/#security-considerations).
- [RFC 5321](https://www.rfc-editor.org/rfc/rfc5321): aceitação e ambiguidades de confirmação no SMTP.

Antes da integração real, confirmar configurações do provedor e versões das dependências. Não usar o teto publicado como ritmo de envio recomendado.

T11: referências Apple 102525 (publicada em 2026-02-03), smtplib Python 3.13 e keyring consultadas em 2026-09-29. Adaptador usa conexão/comandos/autenticação 30s, DATA 300s e QUIT 10s; não registra respostas brutas. Marco submission_started é conservador antes de SMTP.data, inclusive antes do 354. `doctor` autentica mas não negocia envelope nem DATA.

T13: dependências de build também terão constraints exportadas do lock (grupo build). Dados de fila e destinos de exportação/preview/backup recusam raiz do projeto e pastas de sincronização conhecidas por nome. A detecção não substitui escolher armazenamento local; não é possível descobrir todo software de sincronização instalado.

## ADR-007 — Configuração inicial mínima

Por solicitação do usuário, setup pede somente e-mail iCloud e senha específica. Remetente começa igual ao login; assinatura é vazia. A opção --sender mantém suporte ao domínio próprio sem prompt adicional. O comando signature permite configurar/remover assinatura posteriormente sem autenticação. Novos pares de arquivos são publicados por troca atômica da configuração, preservando a consistência e mensagens já importadas.

## ADR-008 — Identidade de envio separada da autenticação

Comando sender configura endereço e nome sem alterar login/Keychain. Nomes por mensagem são campos opcionais no lote e ficam no MIME congelado, sem novas colunas: os campos sender/recipient do banco permanecem endereços do envelope SMTP. Hash de conteúdo considera os cabeçalhos From/To; hash de entrada inclui overrides explícitos. Mudanças de configuração não alteram importações existentes.

## ADR-009 — Sem teto diário local e com espera variável

A pedido do usuário, remover o teto diário local. Não alterar limites do serviço SMTP ou ignorar respostas de throttling. Sortear 15–45 segundos por tentativa, persistir delay_seconds e contar a espera após a conclusão; retomada não sorteia novamente. Configuração antiga continua legível. Manter limites explícitos por execução, cinco tentativas por mensagem e recuperação conservadora.

## ADR-010 — Perfis SMTP iCloud e KingHost

Adicionar provider à configuração, preservando iCloud para configurações legadas. KingHost direto: smtp.kinghost.net, 465, SMTP_SSL com contexto TLS padrão e validação de certificado; sem fallback para conexão sem criptografia. Setup troca conta explicitamente sob lock e preserva o histórico. Senhas permanecem no Keychain por login; login KingHost é a caixa completa. Nome de remetente continua personalizável por mensagem.

Fonte oficial: https://king.host/wiki/artigo/como-configurar-uma-conta-de-email-com-criptografia-tls-ssl/ (consultada em 2026-09-30). Revenda e SMTP internacional usam servidores distintos e não são inferidos automaticamente.

## ADR-011 — Certificados de confiança distribuídos com a aplicação

Usar certifi, com versão fixada e hashes no lock, como conjunto de autoridades para ambos os perfis SMTP. Em 2026-09-30, o bundle padrão do Python neste Mac não continha a raiz GlobalSign R46 usada pela KingHost; a conexão falhava com verify_code 20. O bundle certifi validou três conexões reais sem autenticação. A dependência fornece certificados públicos Mozilla, sem alterar o Keychain ou certificados do sistema. Manter verificação de hostname e CERT_REQUIRED; não aceitar certificados recebidos do servidor como autoridades nem fazer fallback inseguro. Atualizações do bundle devem passar pelo fluxo de atualização das dependências.

## ADR-012 — DKIM local

Usar dkimpy 1.1.8 (e seu dnspython transitivo) para canonicalização, assinatura e verificação padronizadas, evitando implementação criptográfica própria. Gerar RSA 2048 com /usr/bin/openssl via subprocesso sem shell; chave privada somente em memória e no Keychain nativo, em serviço separado. Config.json guarda apenas domínio, seletor, estado e registro público. Verificar assinatura com chave pública local em cada tentativa; ativação verifica DNS. Assinar MIME congelado na fronteira do transporte, sem alterar hashes/idempotência do banco; assinatura pode mudar entre tentativas. Selector gerado com identificador aleatório; setup repetido preserva chave. Rotação fora do escopo. Mudança de conta remove configuração ativa DKIM, mantendo chave antiga no Keychain. Nenhuma promessa de entrega/inbox ou preservação da assinatura pela KingHost até teste recebido.

## ADR-013 — Arquivamento IMAP independente

Usar imaplib da biblioteca padrão e o mesmo contexto TLS/certifi do SMTP; senha pelo backend Keychain existente. Perfil KingHost direto confirmado na [documentação oficial](https://king.host/wiki/artigo/como-configurar-uma-conta-de-email-com-criptografia-tls-ssl/) em 2026-09-30: imap.kinghost.net:993 SSL/TLS. Nenhuma dependência nova. LIST descobre pastas; flag \Sent única permite descoberta automática, caso contrário seleção explícita. Criação/subscrição requer --folder e --create. O programa não configura preferências de pastas do webmail/Mail.

Tabela archives separada de messages, criada na migração 006 sem backfill. No commit de sent inserir pedido e bytes efetivamente passados ao SMTP (incluindo DKIM), garantindo recuperação após queda. APPEND fora de transações, sob worker.lock compartilhado com SMTP e setup. Antes de APPEND, persistir appending. Resposta OK confirma archived; NO/BAD significa failed; desconexão/queda significa uncertain. Search por Message-ID e FETCH PEEK de cabeçalho confirma igualdade exata e preserva flags. Busca vazia após possível aceitação conserva uncertain: IMAP não oferece idempotência transacional e ausência temporária não autoriza duplicação. Não há retry automático de arquivos antigos ao retomar SMTP; archive retry ID é explícito. Resultado de logout não altera aceitação.
