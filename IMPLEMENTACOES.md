# Implementações — branch `Thiago_implementacoes_ECO2026`

Branch de trabalho conjunto para melhorias em toda a plataforma Parâmetro Pedagógico: usabilidade, design,
integrações e serviços. Nada desta branch vai para a `main` sem avaliação conjunta.

`ECO2026`: **eco**ssistema, ciclo de **2026**. O nome não usa acentos para evitar problemas em URLs, gatilhos
de build e ferramentas de linha de comando.

## Regras da branch

- Todo avanço entra no **Registro** abaixo, com data, frente, descrição e commit.
- Commits pequenos e descritivos; uma mudança por commit sempre que possível.
- Testes e verificações do repositório rodam antes de cada push.
- Nenhum dado pessoal, segredo, IP, senha ou detalhe de infraestrutura no repositório.
- Mudanças de banco sempre como migration versionada, nunca aplicadas à mão.

## O ecossistema

A plataforma é o centro de um conjunto de produtos que precisa funcionar como um só para quem usa:

| Produto | Papel no ecossistema |
|---|---|
| Site de acesso | Porta de entrada única (login Firebase) para todos os produtos |
| Plataforma | Avaliações, cartões-resposta, envio e leitura dos cartões, resultados e relatórios |
| Calculadora | Integrada à plataforma, usando os mesmos dados e o mesmo login |
| Assistentes | Apoio contextual para cada perfil, dentro das telas em que a pessoa trabalha |

### Perfis atendidos

| Perfil | O que precisa encontrar primeiro |
|---|---|
| Professor | Suas turmas, avaliações em andamento e resultados dos alunos |
| Coordenador | Visão das turmas e professores da escola, acompanhamento pedagógico |
| Diretor | Indicadores da escola, aplicação das avaliações e pendências |
| Técnico da secretaria | Acompanhamento das escolas da rede, aplicação e envio dos cartões |
| Secretário de Educação | Indicadores consolidados da rede e comparações entre escolas |
| Aluno | Provas disponíveis e seus próprios resultados |
| Equipe PP | Administração da plataforma, catálogo, avaliações e suporte |

Hoje a plataforma tem os papéis `PLATFORM_ADMIN`, `SCHOOL_ADMIN`, `TEACHER` e `STUDENT`, e a hierarquia de
escolas já prevê redes e secretarias (`school_type`). Coordenador, diretor, técnico e secretário ainda não
existem como perfis próprios: definir esses perfis é um dos primeiros itens da frente de serviços.

## Princípios de usabilidade

1. **Um login, uma navegação.** A pessoa não percebe a troca de produto: mesmo menu, mesmo visual.
2. **Começar pelo que a pessoa precisa hoje.** A tela inicial de cada perfil mostra pendências e próximos passos.
3. **A tarefa guia a tela.** Fluxos em etapas claras (criar avaliação → gerar cartões → aplicar → enviar → resultados).
4. **Linguagem da escola, não do sistema.** Termos que professores e gestores já usam; nada de jargão técnico.
5. **Erros que explicam o que fazer.** Toda mensagem de erro diz o motivo e o próximo passo.
6. **Assistente onde a dúvida aparece.** Ajuda contextual na própria tela, ciente do perfil e da página.
7. **Acessível e leve.** Funciona em computadores simples, tablet e celular; contraste e teclado.

## Frentes de trabalho

| Frente | Exemplos |
|---|---|
| Usabilidade | Telas iniciais por perfil, fluxos guiados, mensagens de erro, busca |
| Design | Sistema de design único (componentes, cores, tipografia) para todos os produtos |
| Integrações | Login único Firebase entre produtos, calculadora, geração de cartões, envio e leitura |
| Serviços | Novos perfis, filas de processamento, armazenamento de arquivos, relatórios |

## Registro

| Data | Frente | Repositório | Descrição | Commit | Situação |
|---|---|---|---|---|---|
| 2026-10-16 | Organização | pp-api | Criação da branch e deste registro | (este commit) | Concluído |
