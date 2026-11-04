# Fila de acordes do Acervo dos Rezos

Este programa roda no computador do Caio e analisa os áudios que os
colaboradores enviam pelo app. Enquanto ele estiver aberto, o app mostra
"Computador de análise ligado" e as análises saem em poucos minutos.
Desligado, os pedidos ficam esperando na fila e são feitos quando ele voltar.

## Antes de começar (uma vez só)

1. **Rode o `fila-acordes.sql` no Supabase** (SQL Editor do projeto do Acervo).
   Ele cria a pasta privada dos áudios, a tabela de pedidos e os limites.
2. **Copie a chave service_role**: Supabase > Project Settings > API Keys >
   aba "Legacy API Keys" > `service_role` > Reveal.
   Essa chave dá acesso total ao banco: ela só fica no `config.env` deste
   computador. Não mande para ninguém e não suba para o GitHub.

## Instalar no Windows

1. Coloque esta pasta (`fila-acordes`) em um lugar fixo, por exemplo `C:\Acervo\fila-acordes`.
   Evite pastas sincronizadas (OneDrive): o motor cria uma pasta `.venv` grande.
2. Dê dois cliques em **`instalar.bat`**. Ele instala:
   - o **uv** (gerenciador de Python, que baixa o Python 3.12 sozinho);
   - o **ffmpeg** pelo winget (se pedir, feche a janela e rode o `instalar.bat` de novo);
   - o **motor de acordes** (chordotomy com lv-chordia e Beat This!, cerca de 600 MB);
   - os pesos do Beat This! (81 MB).
3. No fim ele abre o `config.env` no Bloco de Notas: cole a chave service_role
   no lugar de `COLE_AQUI_A_CHAVE_SERVICE_ROLE`, salve e feche.

## Ligar a fila

- **`iniciar-fila.bat`**: abre a janela da fila. Deixe aberta (pode minimizar).
  Se der algum erro, ela se reinicia sozinha em 30 segundos.
- **`iniciar-com-o-windows.bat`**: faz a fila abrir minimizada sempre que você
  entrar no Windows. Para desfazer: `nao-iniciar-com-o-windows.bat`.

Enquanto a janela está aberta, o programa pede ao Windows para **não suspender**
o computador. Ainda assim, deixe o notebook na tomada e com a tampa aberta
(ou configure "Ao fechar a tampa: não fazer nada" nas opções de energia).

## O que acontece com os áudios

O áudio vai para uma pasta privada do Supabase que só a pessoa que enviou e o
admin conseguem ver. Assim que a análise termina (com sucesso ou erro), o
programa apaga o áudio do Supabase e do computador. Fica guardada só a
progressão de acordes (tempos, acordes, tom e BPM estimados).

Limites para não sobrecarregar o computador: 10 análises por pessoa por dia,
3 esperando ao mesmo tempo, arquivos de até 30 MB e músicas de até 12 minutos.
O admin não tem limite.

## Problemas comuns

| O que aparece | O que fazer |
|---|---|
| `Não achei config.env` | Copie `config.exemplo.env` para `config.env` e preencha. |
| `ffmpeg não encontrado` | Rode `instalar.bat` de novo (feche e abra a janela depois de instalar o ffmpeg). |
| `Sem conexão com o Supabase` | Confira a internet. O programa tenta de novo sozinho a cada 30 s. |
| O app diz "computador desligado" com a janela aberta | Veja se a chave service_role está correta no `config.env`. |

O histórico fica em `fila.log`, nesta pasta.

## Atualizar o motor

A versão do chordotomy está fixa em `pyproject.toml` (`0.3.1`). Só troque
depois de testar com algumas músicas conhecidas, e rode `instalar.bat` de novo.
