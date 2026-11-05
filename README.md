# HHRT

Experimentos de compatibilidade seletiva entre mods Fabric e o motor nativo do Horizon Launcher.

> O HHRT não executa arquivos Fabric/Java. O objetivo é identificar o que pode ser carregado como conteúdo Horizon e separar o que exige portagem de código.

## Componentes atuais

### 1. Fabric Scanner

Análise estática de arquivos JAR, sem carregar ou executar bytecode:

- lê fabric.mod.json, IDs, versões e dependências;
- identifica entrypoints e configurações/classes Mixin declaradas;
- detecta classes Java, JARs aninhados e bibliotecas nativas;
- inventaria arquivos em assets/ e data/;
- gera relatório legível ou JSON.

Executar:

    python scanner/hhrt_scanner.py caminho/para/mod.jar
    python scanner/hhrt_scanner.py caminho/para/mod.jar --json

### 2. Conversor de conteúdo Fabric para Horizon

O conversor só aceita JARs classificados como resource_candidate. Ele:

- copia somente arquivos assets/ e data/;
- gera horizon-mod.toml com Content API 0.2;
- registra namespaces adicionais;
- recusa bytecode, entrypoints, Mixins, bibliotecas, dependências Fabric externas e namespaces reservados incompatíveis;
- respeita limites de arquivos e tamanhos documentados pelo Horizon.

Executar:

    python converter/hhrt_convert.py caminho/para/mod.jar --output saida.hmod
    python converter/hhrt_convert.py caminho/para/mod.jar --output saida.hmod --side client

O campo --side aceita client, server ou both (padrão). Escolha o lado de acordo com a função do conteúdo; o padrão não é uma afirmação de que o mod foi validado em multiplayer.

## Testes

Os testes atuais usam JARs sintéticos/isolados para verificar classificação, recusa de código e geração da estrutura ZIP:

    python -m unittest discover -s tests -v

Foi adicionada uma fixture de regressão baseada no manifesto do Witch Client para Minecraft 26.2. O JAR original foi inspecionado localmente, mas não foi enviado ao repositório. A fixture reproduz os metadados relevantes em um JAR sintético; ela ainda precisa ser executada junto da suíte e não substitui testes com mods Fabric reais nem a validação oficial cargo horizon-mod check.

## Limitações conhecidas

- O conversor preserva recursos e dados; não reescreve bytecode nem traduz automaticamente os formatos ou comportamentos específicos de cada mod.
- Dependências Fabric externas são recusadas, em vez de serem ignoradas silenciosamente.
- O pacote produzido usa o formato documentado atualmente como Horizon Content API 0.2.
- A documentação consultada atualmente descreve Minecraft 26.3. Isso não comprova compatibilidade com o APK Android 0.7.7 ou com a meta Minecraft 26.2.
- Antes de instalar, valide o arquivo com cargo horizon-mod check na mesma revisão do Horizon que será usada. Não distribua o arquivo sem conferir o log do jogo.

## Próximos marcos

1. Testar com JARs Fabric reais, começando por mods estritamente de recursos e dados; o Witch Client 1.0.0 já foi inspecionado como caso negativo (exige portagem).
2. Validar os pacotes gerados com o verificador oficial do Horizon.
3. Comparar o comportamento/formatos entre Horizon 0.7.7, as fontes atuais e o alvo futuro 26.2.
4. Só então ampliar a conversão para tipos de dados cuja equivalência esteja documentada.
5. Tratar mods com código Java como portagens individuais para APIs Horizon, nunca como execução direta de JAR.
