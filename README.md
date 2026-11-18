# Daily

Agenda + lista de tarefas para Windows, feita em Python puro (tkinter). Não precisa instalar nada além do Python.

## Como abrir

Dê dois cliques em `daily.pyw` ou rode:

```
pythonw daily.pyw
```

Na primeira vez, o app se registra para **iniciar com o Windows** (chave `HKCU\...\Run`, valor `Daily`). Ao ligar o PC ele abre só o widget (`--startup`). Para desligar isso, clique com o botão direito no widget e desmarque **Iniciar com o Windows**.

## O que tem

- **Widget na área de trabalho**: tarefas de hoje e as atrasadas. Arraste pelo cabeçalho azul.
  - `+` cria uma tarefa para hoje, `↗` abre a janela principal.
  - Clique no círculo para concluir e no texto para editar.
  - Botão direito: abrir, nova tarefa, manter sempre visível, iniciar com o Windows, sair.
  - Por padrão fica atrás das outras janelas, como um widget de área de trabalho.
- **Agenda**: calendário do mês com as tarefas coloridas por categoria. Clique em um dia para ver as tarefas dele e dê dois cliques para criar uma tarefa nesse dia.
- **Tarefas**: busca, filtros (Todas, Em aberto, Concluídas, Canceladas) e filtro por categoria, com a lista agrupada por data.
- **Categorias**: crie, renomeie, troque a cor e remova categorias.
- **Google Agenda** (somente leitura): mostra os eventos do Google na agenda, no painel do dia e no widget.
  - Para conectar, clique em **Google Agenda** na janela principal e cole o endereço secreto iCal. No Google Agenda pelo computador: **⋮** ao lado da agenda → **Configurações e compartilhamento** → **Integrar agenda** → **Endereço secreto no formato iCal**.
  - Atualiza sozinho a cada 15 minutos, ou na hora pelo botão **Atualizar agora**.
  - O que você cria no Daily não vai para o Google.
  - O link fica salvo no `dados.txt`. Trate-o como uma senha: quem tiver o link vê seus eventos. Se vazar, use **Redefinir** no Google.
- Atalhos na janela principal: `Ctrl+N` cria uma tarefa e `Ctrl+F` abre a busca.

Se o app já estiver aberto, abrir de novo só traz a janela para a frente, sem criar outra instância.

## Gerar o .exe (para quem não tem Python)

Dê dois cliques em `build.bat` (ou rode no terminal). Ele cria um ambiente `.venv-build` só para o build, instala o PyInstaller, gera o ícone e cria:

```
dist\Daily.exe
```

Basta enviar esse arquivo (~12 MB). Quem recebe não precisa de Python: é só colocar o `Daily.exe` numa pasta fixa (por exemplo `Documentos\Daily`) e abrir. O `dados.txt` é criado ao lado do `.exe`, ou em `%APPDATA%\Daily` se a pasta não permitir escrita. Na primeira execução ele se registra para iniciar com o Windows.

> Se mudar o `.exe` de pasta, abra-o uma vez no lugar novo para atualizar a inicialização automática.
>
> Por não ser assinado, o Windows pode mostrar "O Windows protegeu o computador". Clique em **Mais informações → Executar assim mesmo**.

## Atualizações automáticas

O `Daily.exe` consulta as [Releases do GitHub](https://github.com/ricsjs/daily/releases) ao abrir e depois a cada 6 horas. Se houver uma versão mais nova:

1. Baixa o novo `Daily.exe` em segundo plano e confere o tamanho e o hash SHA-256.
2. Pergunta se você quer reiniciar agora. Se a resposta for não, a versão nova é instalada na próxima vez que o app abrir (por exemplo, ao ligar o PC).

No menu do widget (botão direito) dá para verificar atualizações manualmente, ligar ou desligar a atualização automática e ver a versão instalada. Rodando como script (`daily.pyw`), o app só avisa que existe versão nova: atualize com `git pull`.

### Publicar uma versão nova

1. Em `daily.pyw`, aumente a `VERSAO` (ex.: `"1.0.0"` → `"1.0.1"`).
2. Rode `build.bat`.
3. No GitHub, abra **Releases → Draft a new release**.
4. Crie a tag `v1.0.1`, com o mesmo número da `VERSAO`.
5. Anexe o `dist\Daily.exe`. O nome precisa ser exatamente `Daily.exe`.
6. Clique em **Publish release**.

Em até 6 horas, ou na próxima vez que abrirem o app, todos recebem a atualização.

## Dados

Tudo fica em `dados.txt` (JSON), na mesma pasta. Dá para editar o arquivo à mão: o app percebe a mudança em alguns segundos. Se o arquivo estiver corrompido ao iniciar, uma cópia é salva como `dados.txt.corrompido`.

Quando o app roda sem console, os erros vão para `erros.log`.
