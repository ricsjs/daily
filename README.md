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

## Dados

Tudo fica em `dados.txt` (JSON), na mesma pasta. Dá para editar o arquivo à mão: o app percebe a mudança em alguns segundos. Se o arquivo estiver corrompido ao iniciar, uma cópia é salva como `dados.txt.corrompido`.

Quando o app roda sem console, os erros vão para `erros.log`.
