<div align="center">

# 💜 Finance Flow

**App de controle financeiro pessoal com contas de usuário, dados isolados por conta e interface estilo fintech.**
Python · Streamlit · Firebase Authentication · Cloud Firestore

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.42+-FF4B4B?logo=streamlit&logoColor=white)
![Firebase](https://img.shields.io/badge/Firebase-Auth%20%2B%20Firestore-FFCA28?logo=firebase&logoColor=black)
![Tests](https://img.shields.io/badge/tests-46%20passing-22C55E)
![Pytest](https://img.shields.io/badge/pytest-ok-0A9EDC?logo=pytest&logoColor=white)

[Demo ao vivo](LINK_DO_APP) · [Reportar bug](../../issues) · [Sugerir melhoria](../../issues)

<!-- Troque pelo seu print/GIF: ![Finance Flow](docs/screenshot.png) -->

</div>

---

## Sumário

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Arquitetura](#arquitetura)
- [Decisões técnicas](#decisões-técnicas)
- [Segurança](#segurança)
- [Modelo de dados](#modelo-de-dados)
- [Testes](#testes)
- [Como rodar](#como-rodar)
- [Deploy](#deploy)
- [Solução de problemas](#solução-de-problemas)
- [Limitações conhecidas](#limitações-conhecidas)
- [Ideias de evolução](#ideias-de-evolução)
- [Sobre o desenvolvimento](#sobre-o-desenvolvimento)

---

## Visão geral

O Finance Flow permite que cada pessoa crie sua conta, registre receitas e despesas e acompanhe **Receita, Despesas e Saldo** em tempo real. O projeto foi pensado para ir além de uma demonstração visual: autenticação real, persistência real, isolamento entre usuários verificado no servidor e uma suíte de testes automatizados.

A tela principal segue três regiões fixas:

1. **Topo:** três indicadores (Receita, Despesas, Saldo), sempre calculados sobre **todos** os dados do usuário, nunca sobre o resultado dos filtros.
2. **Centro:** listagem de movimentações (da mais recente para a mais antiga) com busca, filtros e abas para o gráfico.
3. **Base:** botão de ação flutuante circular **+**, centralizado, que abre o cadastro de movimentação.

## Funcionalidades

**Conta e sessão**
- Cadastro (nome, e-mail, senha, confirmação), login, logout e recuperação de senha, via Firebase Authentication.
- Perfil do usuário salvo no Firestore (`users/{uid}`); se a criação do perfil falhar, a conta recém-criada no Authentication é removida (sem contas "pela metade").
- Mensagens de erro amigáveis e sem enumeração de contas (login e recuperação de senha não revelam se um e-mail existe).

**Movimentações**
- Criar, editar e excluir (com confirmação) receitas e despesas.
- Categorias por tipo, com opção de categoria personalizada.
- Busca por descrição; filtros por tipo, categoria e período.
- Gráfico mensal de receitas × despesas (Plotly).
- Exportação para CSV (compatível com Excel BR e protegida contra *CSV injection*).
- Estado vazio amigável e paginação incremental da lista.

**Interface**
- Tema escuro próprio (paleta roxa/verde/coral), responsivo: os indicadores se reorganizam em telas pequenas.
- Botão **+** é um `st.button` real estilizado por CSS, sem JavaScript falso nem HTML que "parece" botão.

## Arquitetura

```mermaid
flowchart TD
    UI["app.py + views/ + components/<br/>(Streamlit)"] --> SVC_A["services/auth.py<br/>(Firebase Auth REST + Admin SDK)"]
    UI --> SVC_T["services/transactions.py<br/>(regras de negócio)"]
    SVC_A --> FB["database/firebase.py<br/>(único ponto de credenciais)"]
    SVC_T --> FB
    FB --> FS[("Cloud Firestore")]
    SVC_A --> IDP["Firebase Authentication"]
```

```text
finance-flow/
├── app.py                     # entrada e roteamento (login → dashboard → formulário)
├── database/firebase.py       # inicialização do Admin SDK e cliente Firestore
├── services/
│   ├── auth.py                # cadastro, login, reset, sessão e validação de token
│   ├── transactions.py        # CRUD, filtros e totais (checa o dono em toda operação)
│   └── export.py              # CSV
├── components/                # cards, lista de transações, botão +
├── views/                     # telas: auth, dashboard, formulário
├── utils/                     # formatação monetária e ícones
├── styles/main.css            # tema Finance Flow
├── tests/                     # pytest com Firebase simulado em memória
├── firestore.rules            # bloqueia acesso direto de clientes
└── .streamlit/                # config.toml e secrets.toml.example
```

A separação é intencional: **interface não fala com o banco**. Telas chamam `services/`, que chamam `database/firebase.py`. Isso também é o que permite testar tudo com um Firestore falso injetado.

## Decisões técnicas

| Decisão | Por quê |
|---|---|
| **Valores em centavos inteiros** (`amount_cents`) | Evita erros de ponto flutuante com dinheiro. A conversão usa `Decimal` com arredondamento *half-up*. |
| **Criação idempotente** (ID do documento = `form_id` gerado ao abrir o formulário) | Reruns do Streamlit e duplo clique não geram registros duplicados. |
| **Totais sempre globais** | Os filtros só afetam a listagem; os indicadores usam todos os documentos do usuário. |
| **Filtros em Python, consulta única por `user_id`** | Evita índices compostos no Firestore e mantém a consulta simples. Trade-off documentado em [Limitações](#limitações-conhecidas). |
| **Firebase Auth via REST oficial + Admin SDK** | O Streamlit roda no servidor; o REST faz o login e o Admin SDK **verifica** o token. |
| **Datas como string ISO (`YYYY-MM-DD`)** | Ordenam e comparam corretamente como texto e evitam problemas de fuso horário. |
| **Timestamps do servidor** (`created_at`, `updated_at`) | Horário confiável, independente do relógio do cliente. |
| **Erros tipados** (`ValidationError`, `NotFoundError`, `AuthorizationError`, `StorageError`) | A interface mostra mensagens claras e nunca anuncia sucesso sem gravação confirmada. |

## Segurança

- **Senhas** são tratadas exclusivamente pelo Firebase Authentication. Nunca vão para o Firestore, disco ou `session_state`.
- **A identidade é comprovada no servidor.** A cada interação o ID token é verificado com o Admin SDK (e renovado com o refresh token quando expira). O `uid` usado nas operações vem **desse token**, nunca do navegador ou de formulário. Não existe um booleano `logged_in` como prova de identidade.
- **Isolamento entre usuários.** Cada movimentação tem `user_id`. O Admin SDK **ignora** as regras do Firestore, então o código confere o dono em toda leitura, edição, exclusão e cálculo de totais. Acessar documento de outra conta retorna "não encontrada" (sem confirmar que ele existe).
- **Regras do Firestore** (`firestore.rules`) negam todo acesso direto de clientes; só o servidor acessa os dados.
- **Credenciais** ficam em `st.secrets` e fora do Git (`.gitignore` cobre `secrets.toml`, `.env`, `*.json` e ambientes virtuais). O módulo de conexão exibe erros compreensíveis sem vazar a chave.
- **Sem fallback silencioso:** se o Firebase não estiver configurado, o app mostra o motivo e para. Nunca troca por outro banco nem simula uma conexão.
- **CSV injection:** células iniciadas por `=`, `+`, `-`, `@` são neutralizadas na exportação. Conteúdo do usuário é escapado antes de ir para o HTML.
- **Tolerância de relógio** de 60 s na validação do token (máximo permitido pelo Admin SDK), para evitar falsos negativos por pequenas diferenças de horário.

## Modelo de dados

**`users/{uid}`**

| Campo | Tipo | Descrição |
|---|---|---|
| `uid` | string | UID do Firebase Authentication |
| `name` | string | Nome completo |
| `email` | string | E-mail da conta |
| `created_at` / `updated_at` | timestamp | Timestamps do servidor |

**`transactions/{id}`**

| Campo | Tipo | Descrição |
|---|---|---|
| `user_id` | string | UID do dono (usado em toda checagem de autorização) |
| `type` | `"income"` \| `"expense"` | Tipo da movimentação |
| `description` | string | Descrição (até 120 caracteres) |
| `amount_cents` | int | Valor em centavos, sempre `> 0` |
| `category` | string | Categoria (padrão ou personalizada) |
| `date` | string | Data ISO `YYYY-MM-DD` |
| `notes` | string | Observações opcionais |
| `created_at` / `updated_at` | timestamp | Timestamps do servidor (`updated_at` só após edição) |

## Testes

```bash
pytest
```

**46 testes**, todos rodando contra um **Firestore e um Firebase Auth simulados em memória**: nenhum dado ou conta real é tocado. Eles cobrem:

| Área | O que é validado |
|---|---|
| Cálculos | Formatação em R$, conversão sem erro de float, receita/despesa/saldo (ex.: 2.000 − 350 = 1.650), ordenação |
| Persistência | Cadastro de receita e despesa, dados presentes após "reiniciar a conexão", edição e exclusão |
| Validação | Valores zero/negativos/não inteiros, descrição vazia, tipo e data inválidos |
| Idempotência | Salvar duas vezes com o mesmo formulário não duplica |
| Filtros | Filtrar não altera os totais globais |
| Autenticação | Cadastro válido/inválido, e-mail já cadastrado, login, reset sem enumeração, rollback se o perfil falhar |
| Sessão | Logout limpa tudo, token expirado é renovado, token forjado é rejeitado, UID vem do token verificado |
| Isolamento | Usuário B não lê, edita nem exclui dados do usuário A; totais separados por conta |
| Interface | Fluxo ponta a ponta com `streamlit.testing.AppTest`: abrir → **+** → preencher → salvar → listagem e totais atualizados |

## Como rodar

### Pré-requisitos
Python 3.10+, um projeto no [Firebase Console](https://console.firebase.google.com/) e este repositório clonado.

### 1. Configurar o Firebase
1. Crie (ou escolha) um projeto no Firebase.
2. **Firestore Database → Criar banco de dados** (escolha uma localização próxima, ex.: `southamerica-east1`). Em **Regras**, publique o conteúdo de [`firestore.rules`](firestore.rules).
3. **Authentication → Sign-in method → E-mail/senha → Ativar**.
4. **Configurações do projeto → Contas de serviço → Gerar nova chave privada** (baixa um `.json`).
5. **Configurações do projeto → Geral → Seus apps**: registre um app Web e copie a **Chave de API da Web** (pública; não é senha administrativa).

> ⚠️ A chave da conta de serviço tem permissões privilegiadas. Guarde-a só no ambiente confiável do servidor e **nunca** a envie ao GitHub.

### 2. Segredos locais
Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha:

```toml
[firebase]                      # mesmos campos do JSON da conta de serviço
type = "service_account"
project_id = "SEU_PROJECT_ID"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "firebase-adminsdk-xxxxx@SEU_PROJECT_ID.iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"

[firebase_web]
api_key = "SUA_WEB_API_KEY"
```

Use credenciais do **mesmo projeto** nas duas seções. Mantenha `private_key` em uma única linha TOML, com as quebras representadas pelos escapes `\n`; não cole a chave com quebras de linha físicas.

### 3. Instalar e executar

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

### 4. Verificar
Crie uma conta, cadastre uma receita e uma despesa e confira os documentos em `transactions` no console do Firestore. Para testar o isolamento, crie uma segunda conta em uma janela anônima: ela deve ver lista e totais vazios.

## Deploy

Opção mais simples: **Streamlit Community Cloud**.

1. Suba o código para o GitHub **sem** `secrets.toml`.
2. Em [share.streamlit.io](https://share.streamlit.io), crie o app apontando para `app.py`.
3. Em **Settings → Secrets**, cole o conteúdo do seu `secrets.toml`.
4. Antes de divulgar: confirme que as regras do Firestore estão publicadas, dê o mínimo de permissões à conta de serviço, considere restringir a chave de API da Web e decida se o cadastro deve ficar aberto.

## Solução de problemas

| Sintoma | O que fazer |
|---|---|
| Erro ao carregar secrets do Streamlit | Confirme que `.streamlit/secrets.toml` existe e é TOML válido; mantenha `private_key` em uma única linha com escapes `\n`. |
| "Firebase Authentication não está configurado" / `CONFIGURATION_NOT_FOUND` | No Firebase Console do mesmo projeto de `[firebase].project_id` e `[firebase_web].api_key`, abra **Authentication**, clique em **Get started** e, em **Sign-in method**, ative **E-mail/senha**. Depois reinicie o app. |
| "Login por e-mail/senha não está ativado" / `OPERATION_NOT_ALLOWED` | Em **Authentication → Sign-in method**, ative **E-mail/senha** e salve. Confirme que a chave de API pertence ao projeto configurado. |
| "Chave privada malformada" | Copie `private_key` do JSON sem alterar; mantenha os `\n`. |
| "O projeto da conta de serviço é diferente…" | `project_id` e `api_key` precisam ser do mesmo projeto Firebase. |
| "O relógio deste computador está desajustado" | Sincronize data e hora do sistema. |
| `PERMISSION_DENIED` | Verifique o papel da conta de serviço e se ela é do projeto correto. |
| "Database (default) not found" | Crie o banco no Firestore Database. |
| `ModuleNotFoundError` | Ative o venv e rode `pip install -r requirements.txt`. |

## Limitações conhecidas

- **Sessão em memória:** atualizar a página (F5) exige novo login. É mais seguro e simples, mas pode ser trocado por cookie assinado.
- **Filtros e totais em Python:** o app lê todos os documentos do usuário a cada interação. Para milhares de lançamentos, o ideal é paginar e usar agregações do Firestore.
- **Verificação de dono e escrita não são atômicas:** a checagem de propriedade e a escrita são duas operações; para cenários de alta concorrência, usar transações do Firestore.
- **Sem verificação obrigatória de e-mail** no cadastro.
- Os testes usam Firebase simulado; o comportamento contra um projeto real depende da configuração correta (ver solução de problemas).

## Ideias de evolução

- Verificação de e-mail e login social
- Orçamentos e metas por categoria
- Movimentações recorrentes
- Importação de extratos (CSV/OFX)
- Sessão persistente com cookie assinado
- Agregações no Firestore e paginação por cursor
- Testes de regras do Firestore com o Emulator Suite

## Sobre o desenvolvimento

Este projeto foi construído com **IA generativa** (vibe coding) durante o curso de **implementação de IA generativa aplicada à programação**, no **SENAI Alumínio**, com o objetivo de aprender mais sobre construção de software e **engenharia de prompt**. O método foi: especificar requisitos e critérios de aceite em prompts detalhados, gerar o código, **executar os testes, revisar e corrigir** o que voltou. Incluindo depurar problemas reais de integração, como a validação de tokens com diferença de relógio.

## Autor

**Enzo** · [LinkedIn](https://www.linkedin.com/in/devbyenzo) · [GitHub](https://github.com/devbyenzo)

## Licença
Projeto sob a licença MIT.
