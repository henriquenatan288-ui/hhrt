# HHRT

Experimentos de compatibilidade seletiva entre mods Fabric e o motor nativo do Horizon Launcher.

## Estado do projeto

O primeiro componente é o **HHRT Fabric Scanner**: um analisador estático de arquivos `.jar`.
Ele lê metadados e estrutura do pacote sem carregar nem executar bytecode Java.

## Fabric Scanner (v0.1.0)

Requisitos: Python 3.11 ou superior. Não há dependências externas.

Executar diretamente:

```bash
python scanner/hhrt_scanner.py caminho/para/mod.jar
```

Gerar relatório JSON:

```bash
python scanner/hhrt_scanner.py caminho/para/mod.jar --json
```

O scanner identifica:

- metadados `fabric.mod.json`, IDs, versões e dependências;
- entrypoints declarados;
- configurações e classes Mixin declaradas;
- classes Java, recursos e bibliotecas nativas;
- caminhos suspeitos no arquivo ZIP, ignorados na análise.

### Classificações

- `resource_candidate`: sem classes Java, entrypoints ou Mixins detectados; candidato a revisão/conversão de recursos.
- `requires_port`: contém bytecode Java ou entrypoints e exige portagem.
- `requires_port_or_incompatible`: declara Mixins e não pode ser executado diretamente no Horizon.

As classificações são heurísticas, não certificações. O scanner **não executa JARs**, não converte arquivos para `.hmod` e não resolve dependências.

## Direção técnica

1. Scanner e relatório de compatibilidade.
2. Inventário e validação de recursos candidatos.
3. Conversor seletivo para formatos suportados pelo Horizon.
4. Adaptadores de código apenas quando houver API Horizon equivalente.
5. Matriz de testes por versão do Horizon e do Minecraft, incluindo a meta futura 26.2.

O APK Horizon Android 0.7.7 é tratado como referência de análise, não como prova de que APIs documentadas em versões posteriores existam nessa build.
