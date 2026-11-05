# Relatório de portabilidade — Witch Client 1.0.0

**Data da análise:** 5 de novembro de 2026  
**Projeto:** HHRT — camada seletiva de compatibilidade Fabric para Horizon  
**Arquivo analisado:** witch-client-light-1.0.0.jar (inspeção local; não incluído no repositório)  
**Alvo declarado pelo mod:** Minecraft `~26.2`

## 1. Resultado executivo

**Classificação HHRT: `requires_port_or_incompatible`.**

O Witch Client não pode ser convertido integralmente para um content mod `.hmod`. O arquivo contém lógica Java, inicializador Fabric, dependência Fabric API e Mixins que alteram pontos internos do cliente Minecraft. O formato `.hmod` atual aceita dados e recursos, não executa bytecode Java. A alternativa documentada no Horizon upstream é uma portagem individual para um native mod `.hnmod`, escrito em Rust e acoplado a uma revisão específica do motor.

A análise encontrou oportunidades reais de reimplementação para interface, HUD, ESP, tracers, partículas, câmera, filtros e utilitários. Isso não significa compatibilidade pronta: cada recurso precisa ser reescrito e validado contra a mesma revisão do motor que o launcher realmente executa.

**Decisão:** manter o JAR original fora do pipeline de conversão; usar o Witch como especificação funcional para portagens seletivas.

## 2. Evidências extraídas do JAR

| Item | Resultado |
|---|---:|
| ID / versão | `witch` / `1.0.0` |
| Ambiente | Client |
| Dependência Minecraft | `~26.2` |
| Fabric Loader | `>=0.19.0` |
| Java | `>=25` |
| Fabric API | `*` (obrigatória) |
| Classes Java | 113 |
| Arquivos em assets/ e data/ | 830 |
| Arquivos em assets/minecraft/ | 820 |
| Arquivos em assets/witch/ | 10 |
| Arquivos em data/ | 0 |
| Entrypoints | 1: `com.witch.WitchClient` |
| Configurações Mixin | 1: `witch.mixins.json` |
| Mixins client declarados | 14 |

A configuração Mixin usa `JAVA_25`, declara `required: false` e define `defaultRequire: 0`. Isso torna algumas injeções tolerantes à ausência de pontos de injeção, mas **não** remove a dependência do ecossistema Fabric/Mixin nem torna o JAR executável no Horizon.

### 2.1 Pontos internos do Minecraft modificados pelos Mixins

A inspeção estática do bytecode identificou estes alvos:

| Mixin | Alvos observados | Área afetada |
|---|---|---|
| CameraMixin | Camera.update, Camera.getMaxZoom, GameRenderer.extractRenderState, GameRenderer.calculateFov | Freecam, freelook, zoom e câmera |
| GameRendererMixin | GameRenderer.bobHurt | Hurt camera |
| LevelLoadingScreenMixin | LevelLoadingScreen.extractRenderState / extractBackground | Tela de carregamento de mundo |
| ConnectScreenMixin | ConnectScreen.extractRenderState | Tela de conexão |
| LoadingOverlayMixin | LoadingOverlay.extractRenderState / extractProgressBar | Overlay, barra e marca da tela de carregamento |
| ScreenBackgroundMixin | Screen.extractBackground | Fundo das telas |
| ChatComponentMixin | ChatComponent.addMessage | Timestamp do chat |
| LivingEntityMixin | LivingEntity.getCurrentSwingDuration | Duração do swing |
| SkyRendererMixin | SkyRenderer.extractRenderState | Céu |
| FogRendererMixin | FogRenderer.setupFog | Neblina |
| MinecraftGlowMixin | Minecraft.shouldEntityAppearGlowing | Decisão de glow |
| EntityGlowColorMixin | Entity.getTeamColor | Cor do glow |
| MouseHandlerMixin | MouseHandler.turnPlayer | Rotação do jogador / freelook |
| MultiPlayerGameModeMixin | destroyBlock, continueDestroyBlock, startDestroyBlock | Delay de quebra e ghost blocks |

Os alvos confirmam que parte relevante do client modifica o fluxo interno de renderização, câmera, chat e interação. Não é apenas uma coleção de texturas.

## 3. Mapeamento de recursos para Horizon

O mapeamento abaixo usa como referência a documentação pública atual do Horizon upstream. Os nomes de hooks e APIs citados são **candidatos para portagem**, não prova de que estejam presentes no APK Android 0.7.7.

| Grupo do Witch Client | Classes/módulos identificados | Caminho de portagem no Horizon | Avaliação |
|---|---|---|---|
| ClickGUI e telas | ClickGuiScreen, HudEditScreen, GuiSettingsModule, WitchTitleScreen, WitchLoading, WitchThemeModule | Native screen própria, desenho pós-tela e hooks de mouse/teclado; reconstruir layout, animações e estado em Rust | **Portável com reimplementação** |
| HUD | ArmorHudModule, CoordsHudModule, AntiVanishModule, WaypointsModule e alertas dos finders | Hook de HUD e helpers de texto/desenho; obter dados do jogador e do mundo no lado cliente | **Portável; dados precisam ser mapeados** |
| Crosshair e chat | CrosshairModule, ChatTimestampsModule | HUD próprio para mira; para timestamps, hook específico no fluxo de mensagens ou renderização | **Parcial; chat exige hook dedicado** |
| ESP e tracers | PlayerEspModule, GlowPlayersModule, TracersModule | WorldPrimitives para linhas, caixas e texto; native_world_drawn/native_render_needs quando for necessária geometria por entidade | **Boa candidata para primeira portagem visual** |
| ESP de blocos e scanners | FarmEspModule, StorageEspModule, ChunkBordersModule, LightLevelModule, AncientFinderModule, SusChunkFinderModule, SusHoleFinderModule, SusSoloFinderModule, WaypointsModule | Leitura de estado/posição do mundo, cache incremental e WorldPrimitives para desenhar resultados | **Portável com trabalho de dados e desempenho** |
| X-Ray | XRayModule | Exige mais que desenhar caixas: precisa controlar quais superfícies/blocos entram na renderização ou implementar uma visualização equivalente | **Alta complexidade; sem equivalência simples confirmada** |
| Efeitos de mundo | BreakWaveModule, JumpCirclesModule, AmbientDustModule, ParticlesModule, CardParticlesModule | WorldPrimitives para formas simples; ParticleEngine::controlled e ParticleController para partículas com estado e interpolação | **Portável por reimplementação** |
| Céu, neblina e clima | SkyModule, FogModule, WeatherOffModule | Shader API para estágio sky/weather/post; native_render_fog para ajustar FogData | **Caminho técnico identificado; confirmar versão** |
| Filtros e iluminação | FilterModule, MoodFilterModule, FullbrightModule | Shader API: material/post e parâmetros de luz; evitar alterar opções globais do jogo sem necessidade | **Parcial; depende do efeito pretendido** |
| Zoom | ZoomModule | native_compute_fov_modifier (hooks API 362) ou native_compute_fov (API 109) | **Boa candidata isolada** |
| FreeLook / Freecam | FreeLookModule, FreecamModule | O hook de input e a leitura native_camera ajudam; a API documentada de câmera é uma leitura da câmera, não um setter de câmera livre | **Exige hook de câmera e input mais profundo** |
| Movimento | AutoSprintModule, FlyModule, SpeedModule, SpiderModule, StepModule, BoatFlyModule, JesusModule, NoFallModule | native_movement_input (hooks API 360) cobre forward/strafe/jump/sneak; física, colisão, voo e dano exigem hooks separados | **Portagem individual; não coberta por um único hook** |
| Inventário e ações | AutoEatModule, AutoToolModule, AutoTotemModule, TriggerBotModule | Reimplementar seleção/uso de itens e ações de combate com APIs específicas; não há conversor de lógica Fabric | **Exige hooks de ação; equivalência completa não confirmada** |
| Quebra e combate | BreakDelayModule, NoGhostBlocksModule, SlowHitModule, NoHurtCamModule, HideNameModule | Hooks nos pontos de ação/render correspondentes; native_render_name_tag ajuda a controlar name tags, mas não resolve os outros comportamentos | **Portagem pontual** |
| Conexão e estado do servidor | AutoReconnectModule, AntiVanishModule | Eventos de conexão/estado e leitura de pacotes podem ajudar; native_client_packet é observacional e não substitui todos os eventos de sessão | **Parcial; requer análise do fluxo de rede** |

### 3.1 APIs upstream com correspondência útil

- **Renderização 3D:** `native_world_primitives` desenha linhas, contornos, caixas preenchidas, beams e texto em coordenadas do mundo. Primitivas podem usar `.through_walls()`. É o melhor ponto inicial para tracers, ESP, waypoints e marcadores.
- **Geometria por entidade:** `native_world_drawn` fornece buffers, matrizes, profundidade e geometria; `native_render_needs` permite solicitar separação por entidade e profundidade. Útil para efeitos mais avançados, mas exige mais código gráfico.
- **HUD e telas:** o catálogo contém o hook `hud`; `native_screen_render_post` desenha sobre telas; `native_mod_screen_open` abre uma tela própria. Há hooks de mouse, teclado, texto e rolagem.
- **Câmera e zoom:** `native_compute_fov_modifier` altera a escala de FOV; `native_camera()` fornece uma fotografia dos dados da câmera, mas não é uma API de controle de câmera livre.
- **Fog:** `native_render_fog` altera o FogData final após os cálculos normais do ambiente.
- **Partículas:** `ParticleEngine::controlled` permite criar partículas controladas por código; o controlador precisa atualizar estado e expiração. O suporte atual também descreve curvas lineares de tamanho/opacidade para certos comportamentos declarativos.
- **Shaders:** a Shader API 0.1 declara estágios sky, vertex, material, weather e post. É uma superfície própria, separada do conversor `.hmod`.

## 4. Problema dos recursos em assets/

O JAR tem 820 arquivos no namespace `minecraft`, incluindo substituições de fontes e texturas vanilla. O formato Content API 0.2 documentado atualmente não aceita `assets/minecraft/` genérico em content mods; a exceção documentada é um subconjunto de tags em `data/minecraft/tags/`.

Os 10 arquivos sob `assets/witch/` são um conjunto separado de recursos próprios (fonte, idioma, logo e sprites). Eles são candidatos a extração/reempacotamento, desde que sejam conferidos os formatos e a licença de cada arquivo. Isso não salva a lógica Java e não permite converter o JAR completo.

**Ação recomendada:** separar os assets próprios dos overrides vanilla; não importar os 820 overrides automaticamente. A rota de resource pack, se utilizada, deve ser testada separadamente da rota `.hmod`.

## 5. Compatibilidade de versão e plataforma

Há duas diferenças que impedem declarar compatibilidade:

1. O Witch Client declara Minecraft `~26.2` e Java `>=25`.
2. A documentação pública atual do Horizon upstream descreve os formatos de conteúdo e APIs tendo Minecraft 26.3 como referência. Isso não prova que os mesmos contratos existam em 26.2.

Além disso, o Horizon Android 0.7.7 é uma distribuição Android própria. As notas de lançamento de 2 de novembro de 2026 citam melhorias Vulkan/OpenGL ES e mods integrados opcionais (Zoom, Minimap, Recipes e SmartF3), mas não documentam suporte geral a JARs Fabric nem confirmam que as APIs native-mods do Horizon upstream desktop estejam presentes no APK.

Portanto, o relatório não trata nenhuma API upstream como disponível no APK 0.7.7 até que seja conferida diretamente contra o código/artefatos daquela versão.

## 6. Ordem recomendada para portagem

A sequência recomendada reduz risco e permite validar a arquitetura antes dos módulos mais invasivos:

1. **Prova de HUD:** portar CoordsHud e ArmorHud; validar leitura de dados, escala, âncora e atualização.
2. **Prova de renderização 3D:** portar Tracers e PlayerESP usando WorldPrimitives; validar profundidade, through-walls, coordenadas interpoladas e custo por frame.
3. **Prova de tela:** portar ClickGUI mínima com categorias, toggles, settings, scroll e persistência; não tentar reproduzir todos os shaders na primeira versão.
4. **Prova de shader/partículas:** portar Fog/Sky como opções independentes e uma partícula com fade; testar shader API e o motor Android separadamente.
5. **Módulos de movimento e ações:** só depois de identificar hooks específicos para cada comportamento; testar em mundo local antes de considerar multiplayer.
6. **X-Ray e scanners:** tratar como projeto separado de renderização/leitura de mundo, com limites de CPU, cache por chunk e telemetria de desempenho.

## 7. Bloqueios e critérios de aceite

Antes de iniciar uma portagem de produção:

- [ ] Identificar a revisão exata do motor contida no APK Horizon Android 0.7.7.
- [ ] Confirmar se o APK inclui o catálogo de native hook points e quais versões de hooks estão disponíveis.
- [ ] Confirmar a versão da Content API e a versão do formato de recursos usada pelo APK.
- [ ] Confirmar se a build Android aceita a mesma toolchain de native mods/horizon-mixins do upstream.
- [ ] Fixar uma revisão que corresponda ao alvo Minecraft 26.2; não assumir que documentação 26.3 seja retrocompatível.
- [ ] Validar uma portagem mínima no Android, incluindo renderização GLES/Vulkan e entrada por toque.
- [ ] Só depois ampliar o scanner para sugerir automaticamente módulos e dependências a portar.

## 8. Conclusão

O Witch Client é um **caso de portagem**, não um caso de conversão. A melhor primeira vertical slice é **CoordsHud → Tracers → PlayerESP → ClickGUI**. São recursos úteis para provar o caminho de dados, renderização e UI sem começar por X-Ray, Freecam ou automações de interação.

O relatório não altera o APK, não compila native mods e não distribui o JAR do Witch Client.

## Fontes primárias consultadas

- Horizon — [Horizon APIs](https://github.com/horizon-rust/horizon/blob/main/docs/api/README.md)
- Horizon — [Horizon mods / Content API 0.2 e native mods](https://github.com/horizon-rust/horizon/blob/main/docs/mods.md)
- Horizon — [Native mods e hook points](https://github.com/horizon-rust/horizon/blob/main/docs/native-mods.md)
- Horizon — [Shader API reference 0.1](https://github.com/horizon-rust/horizon/blob/main/docs/api/shaders-reference.md)
- Horizon Android — [Release 0.7.7](https://github.com/Vasysik/horizon-android/releases/tag/v0.7.7)

**Nota de proveniência:** documentação upstream consultada em 5 de novembro de 2026; a branch/documentação upstream é mutável. Para produção, os arquivos de referência e seus commits precisam ser fixados junto à revisão do motor escolhida.
