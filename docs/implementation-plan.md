# Plano de implementação

Implementação T01–T13 verificada em 2026-09-29; teste real T14/AC-22 posteriormente confirmado pelo usuário com imagens do recebimento. Evidências detalhadas em TASKS.md.

A execução detalhada é controlada em [TASKS.md](../TASKS.md), com dependências, critérios de conclusão e registro de evidências. Este documento mantém a visão geral por etapas.

## Etapa 1 — Base e contrato da CLI

- [x] Criar pacote, ambiente uv, comando `mailqueue` e testes.
- [x] Implementar diretório de dados, configuração, erros e envelope JSON.
- [x] Criar migração inicial e backup SQLite.
- [x] Verificar AC-16 e AC-17.

Conclusão: CLI consulta banco vazio e gera backup, sem qualquer capacidade de envio real.

## Etapa 2 — Importação e composição

- [x] Implementar validação JSON/CSV, IDs estáveis e importação atômica.
- [x] Compor HTML/texto com assinatura e MIME congelado.
- [x] Implementar listagem, consulta, cancelamento e exportação.
- [x] Implementar preview HTML protegido e EML.
- [x] Verificar AC-01 a AC-05.

Conclusão: IA prepara e revisa uma fila persistente; reimportação não duplica.

## Etapa 3 — Worker com transporte simulado

- [x] Implementar lock exclusivo, execuções, pausa e retomada.
- [x] Implementar limites persistentes, orçamento de submissões e retries.
- [x] Implementar fases de tentativa, recuperação e resolução de incertos.
- [x] Testar AC-07 a AC-10, AC-12 a AC-15 e AC-18 a AC-20.

Conclusão: comportamento da fila validado sob interrupções, antes de integrar credenciais reais.

## Etapa 4 — iCloud e Keychain

- [x] Implementar setup seguro, doctor e backend nativo do Keychain.
- [x] Implementar transporte SMTP com TLS e classificação de falhas por fase.
- [x] Implementar cópias de teste idempotentes.
- [x] Verificar AC-06, AC-11 e AC-21 com componentes simulados.
- [x] Executar AC-22: envio autorizado e recebimento confirmados, sem assinatura personalizada.

Estado: componentes verificados por simulação e integração real confirmada na T14/AC-22.

## Etapa 5 — Operação por IA e entrega

- [x] Validar um fluxo completo com lote fictício e transporte simulado pela CLI.
- [x] Documentar instalação, atualização, backup e comandos efetivamente disponíveis.
- [x] Preparar instruções curtas para a IA: importar, revisar, iniciar e consultar.
- [x] Verificar que nenhum teste ou exemplo contém dados pessoais ou credenciais.
- [x] Atualizar README e este plano com o estado real e limitações remanescentes.

Conclusão: usuário consegue operar por linguagem natural através da IA, com a CLI como interface estável.

## Política de mudanças

Mudanças em escopo, estados, idempotência ou limites exigem atualizar a especificação, o contrato e os cenários relacionados. Não ampliar a primeira versão para serviços permanentes ou interfaces adicionais sem necessidade concreta.

## Etapa 6 — Arquivo IMAP KingHost

- [x] T16: implementar e verificar REQ-16 / AC-29 por serviços simulados.
- [x] T17: configurar/verificar IMAP real sem SMTP/APPEND, AC-30.
- [x] T18: conferir primeiro arquivo real após autorização explícita de teste nesta conversa. Leitura IMAP confirmou cópia única e bytes; apresentação visual nos clientes ainda aguarda usuário.
