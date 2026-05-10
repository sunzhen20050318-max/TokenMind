/**
 * Central UI string dictionary. Every user-facing string lives here keyed
 * by section + key, with `zh` and `en` siblings. Components accept a
 * `lang` prop and read `STRINGS.section.key[lang]`.
 *
 * Two routes render the page: `/` (zh, default) and `/en/` (en). Both
 * import the same components and pass a different `lang` prop, so adding
 * copy = editing one file here.
 */

export type Lang = 'zh' | 'en';

export const STRINGS = {
  meta: {
    title: {
      zh: 'TokenMind · 本地优先的 AI Agent 工作台',
      en: 'TokenMind · Local-first AI agent workbench',
    },
    description: {
      zh: '本地优先的 AI Agent 框架。多模型、多渠道、可扩展工具系统，跑在你自己的电脑上。',
      en: 'A local-first AI agent framework. Multi-model, multi-channel, extensible tools — running on your own machine.',
    },
  },

  nav: {
    features: { zh: '能力', en: 'Features' },
    channels: { zh: '渠道', en: 'Channels' },
    install: { zh: '安装', en: 'Install' },
    download: { zh: '下载', en: 'Download' },
    githubLabel: { zh: 'GitHub 仓库', en: 'GitHub repository' },
    giteeLabel: { zh: 'Gitee 仓库', en: 'Gitee repository' },
    emailLabel: { zh: '联系邮箱', en: 'Contact email' },
    homeLabel: { zh: 'TokenMind 首页', en: 'TokenMind home' },
    langSwitch: { zh: 'EN', en: '中' },
    langSwitchLabel: { zh: '切换到英文', en: 'Switch to Chinese' },
  },

  hero: {
    headline: {
      zh: '新一代 AI Agent，跑在你自己的电脑上。',
      en: 'Next-gen AI agents, running on your own machine.',
    },
    tagline: {
      zh: '本地优先 · 多模型 · 多渠道 · 开箱即用',
      en: 'Local-first · Multi-model · Multi-channel · Works out of the box',
    },
    macos: { zh: '下载 macOS 版', en: 'Download for macOS' },
    windows: { zh: '下载 Windows 版', en: 'Download for Windows' },
    scroll: { zh: '向下滚动', en: 'Scroll' },
  },

  feature: {
    onDevice: { zh: '本机运行', en: 'On device' },
    a: {
      eyebrow: { zh: '立场', en: 'The stance' },
      title: {
        zh: '你的，永远不离开你。',
        en: 'Yours. It never leaves you.',
      },
      body: {
        zh: '对话、记忆、文档、向量库 —— 全部只活在你这台机器里。无账号，无云端，无遥测。',
        en: 'Conversations, memory, documents, vectors — they live only on your machine. No account. No cloud. No telemetry.',
      },
      // Quote-style accent character (left-side double quote in serif).
      accent: '"',
    },
    b: {
      eyebrow: { zh: '开放', en: 'Open' },
      title: {
        zh: '像你的编辑器一样可改造。',
        en: 'Hack it like your editor.',
      },
      body: {
        zh: 'MIT 开源，MCP 原生，skill 与 tool 完全可自定义。不锁定任何模型，不锁定任何渠道。',
        en: 'MIT licensed. MCP-native. Skills and tools fully extensible. Locked to no model, no platform.',
      },
      accent: '⌘',
    },
  },

  tools: {
    eyebrow: { zh: '能力栈', en: 'Capabilities' },
    title: { zh: '一个 Agent，全套工具。', en: 'One agent. Every tool.' },
    body: {
      zh: '文件、Shell、Web、MCP、知识库、记忆、定时任务 —— 内建可用，无需拼装第三方插件。',
      en: 'Filesystem, shell, web, MCP, knowledge, memory, cron — built in, not bolted on.',
    },
    items: [
      {
        name: { zh: 'Shell 命令', en: 'Shell' },
        desc: {
          zh: '直接执行 shell，高风险命令可由你二次确认。',
          en: 'Execute shell commands. High-risk calls go through user approval.',
        },
      },
      {
        name: { zh: '文件系统', en: 'Filesystem' },
        desc: {
          zh: '读、写、编辑、列出本地文件 —— 不离开本机。',
          en: 'Read, write, edit, list local files — never leaves the box.',
        },
      },
      {
        name: { zh: 'Web', en: 'Web' },
        desc: {
          zh: '搜索 + 抓取，自带 SSRF 与内网保护。',
          en: 'Search and fetch, with built-in SSRF and private-IP guards.',
        },
      },
      {
        name: { zh: 'MCP', en: 'MCP' },
        desc: {
          zh: 'stdio · SSE · streamable HTTP 三种传输全支持。',
          en: 'All transports supported: stdio, SSE, streamable HTTP.',
        },
      },
      {
        name: { zh: '知识库', en: 'Knowledge' },
        desc: {
          zh: '多格式文档、混合检索、来源引用。',
          en: 'Multi-format docs, hybrid retrieval, source citations.',
        },
      },
      {
        name: { zh: '记忆系统', en: 'Memory' },
        desc: {
          zh: '长期记忆 + 历史归档，按 token 阈值自动整合。',
          en: 'Long-term facts + history log, consolidated automatically.',
        },
      },
      {
        name: { zh: '定时任务', en: 'Cron' },
        desc: {
          zh: '按计划唤醒 Agent，自动跑任务并回写结果。',
          en: 'Wake the agent on a schedule, run tasks, deliver results.',
        },
      },
      {
        name: { zh: '创作能力', en: 'Creative' },
        desc: {
          zh: '图像、音乐、TTS、声音克隆 —— 一键生成。',
          en: 'Image, music, TTS, voice cloning — generate in-chat.',
        },
      },
    ],
  },

  channels: {
    eyebrow: { zh: '全渠道接入', en: 'Wherever you talk' },
    title: {
      zh: '在你已经在用的地方使用。',
      en: 'Meet you where you already are.',
    },
    body: {
      zh: '桌面客户端、Web 控制台、所有主流 IM —— 接入即用。',
      en: 'Desktop, web console, every major messenger — drop in and go.',
    },
    items: [
      { name: 'Web', tag: { zh: '内置', en: 'Built-in' } },
      { name: 'Telegram', tag: { zh: 'Bot', en: 'Bot' } },
      { name: 'WhatsApp', tag: { zh: 'Baileys', en: 'Baileys' } },
      { name: 'Email', tag: { zh: 'IMAP/SMTP', en: 'IMAP/SMTP' } },
      { name: 'Feishu', tag: { zh: '飞书', en: 'Lark' } },
      { name: 'DingTalk', tag: { zh: '钉钉', en: 'Stream' } },
      { name: 'WeCom', tag: { zh: '企业微信', en: 'AIBot' } },
      { name: 'QQ', tag: { zh: '官方机器人', en: 'Bot' } },
    ],
  },

  useCases: {
    eyebrow: { zh: '适用场景', en: 'Built for' },
    title: { zh: '一个工具，多种用法。', en: 'One tool, many patterns.' },
    items: [
      {
        kicker: { zh: '开发者', en: 'For developers' },
        title: {
          zh: '把它变成你的命令行副驾。',
          en: 'A copilot that lives in your terminal.',
        },
        body: {
          zh: '通过 MCP 接你自己的 API、操作本地仓库、自动化脚本，全程在本地完成。',
          en: 'Plug your own APIs in via MCP, run scripts, drive your local repo — all on device.',
        },
      },
      {
        kicker: { zh: '团队', en: 'For teams' },
        title: {
          zh: '让团队群里直接调用 Agent。',
          en: 'Share an agent inside the team chat.',
        },
        body: {
          zh: '接入 Feishu / 钉钉 / 企业微信，统一知识库与团队记忆，权限与审批可控。',
          en: 'Connect Feishu / DingTalk / WeCom; share the knowledge base and audit every tool call.',
        },
      },
      {
        kicker: { zh: '研究者', en: 'For researchers' },
        title: {
          zh: '长任务、长上下文、可追溯。',
          en: 'Long tasks, long context, traceable answers.',
        },
        body: {
          zh: '阅读 PDF、整理资料、跑批量分析，每条引用都能溯源到原文位置。',
          en: 'Read PDFs, organise sources, run batch analyses — every citation traces back to the page.',
        },
      },
    ],
  },

  providerStrip: {
    eyebrow: {
      zh: '兼容主流大模型与本地推理',
      en: 'Works with every major model & local runtime',
    },
  },

  install: {
    eyebrow: { zh: '三步开跑', en: 'Three steps' },
    title: { zh: '下载，双击，开始用。', en: 'Download. Double-click. Done.' },
    body: {
      zh: '不用写代码，不用配环境，下完安装包双击就能用。',
      en: 'No code, no toolchain. Grab the installer, double-click, you are in.',
    },
    osLabels: {
      macos: { zh: 'macOS', en: 'macOS' },
      windows: { zh: 'Windows', en: 'Windows' },
    },
    steps: [
      {
        kicker: { zh: '下载安装包', en: 'Download' },
        title: { zh: '挑你的系统', en: 'Pick your platform' },
        note: {
          zh: '约 80MB · 推荐使用最新稳定版。',
          en: 'About 80MB · always grab the latest stable build.',
        },
        macos: {
          zh: 'macOS 12+（Apple Silicon / Intel 通用）',
          en: 'macOS 12+ (Apple Silicon / Intel · universal)',
        },
        windows: {
          zh: 'Windows 10/11（x64 安装包）',
          en: 'Windows 10/11 (x64 installer)',
        },
        macosLabel: { zh: '下载 macOS · DMG', en: 'Download macOS · DMG' },
        windowsLabel: { zh: '下载 Windows · EXE', en: 'Download Windows · EXE' },
      },
      {
        kicker: { zh: '运行安装包', en: 'Install' },
        title: {
          zh: '系统标准的安装方式即可',
          en: 'Whatever your OS already does',
        },
        note: {
          zh: '首次打开时按系统提示授权即可，无需关闭安全保护。',
          en: 'Authorise it the way your OS asks the first time. No need to disable any security setting.',
        },
        macos: {
          zh: '挂载 DMG，把图标拖进 Applications 文件夹',
          en: 'Mount the DMG, drag the icon into your Applications folder',
        },
        windows: {
          zh: '双击 EXE 安装向导，一路下一步',
          en: 'Double-click the EXE wizard, next → next → finish',
        },
      },
      {
        kicker: { zh: '启动 Agent', en: 'Launch' },
        title: {
          zh: '双击应用 → 浏览器立刻进入',
          en: 'Double-click → your browser jumps right in',
        },
        note: {
          zh: '应用会在本机启动一个服务（默认 http://localhost:18888），关掉应用即停止服务。',
          en: 'The app boots a local service at http://localhost:18888. Quit the app to stop it.',
        },
        macos: {
          zh: '从 Launchpad 或 Applications 双击 TokenMind',
          en: 'Open it from Launchpad or your Applications folder',
        },
        windows: {
          zh: '从开始菜单或桌面快捷方式双击',
          en: 'Open it from the Start menu or desktop shortcut',
        },
      },
    ],
  },

  cta: {
    title: {
      zh: '现在就把 AI 跑在自己的电脑上。',
      en: 'Run your AI on your own machine — today.',
    },
    body: {
      zh: '完全免费 · MIT 开源 · macOS / Windows / Linux 全平台支持',
      en: 'Free · MIT open source · macOS / Windows / Linux',
    },
  },

  footer: {
    // Brand-led footer styled after Antigravity's: a short tagline (left),
    // a flat list of links (no headers), then a giant wordmark across the
    // page, and a thin meta strip at the very bottom. The link labels are
    // intentionally English-only — they're product-facing nouns that read
    // the same in both routes, and skipping translation keeps the footer
    // visually identical to the brand mark above it.
    tagline: {
      zh: 'Run AI on your own machine.',
      en: 'Run AI on your own machine.',
    },
    // Flat link lists. Order is shown left → right within each column.
    primaryLinks: ['Download', 'Docs', 'GitHub', 'Gitee'],
    secondaryLinks: ['License', 'Changelog', 'Contact'],
    // Bottom meta strip — small links beside the brand mark.
    metaLinks: ['MIT License', 'Privacy', 'Contact'],
  },
} as const;
