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
      zh: '每一个 token，都从你的机器里经过。',
      en: 'Every token passes through your machine.',
    },
    tagline: {
      zh: '本地优先的 AI Agent 框架，支持多模型与多渠道',
      en: 'A local-first AI agent framework. Many models, many channels.',
    },
    macos: { zh: '下载 macOS 版', en: 'Download for macOS' },
    windows: { zh: '下载 Windows 版', en: 'Download for Windows' },
    scroll: { zh: '向下滚动', en: 'Scroll' },
  },

  feature: {
    onDevice: { zh: '本机运行', en: 'On device' },
    a: {
      eyebrow: { zh: '隐私', en: 'Privacy' },
      title: {
        zh: '所有数据，只在本机。',
        en: 'Everything stays on your machine.',
      },
      body: {
        zh: '对话、记忆、文档、向量库都存在本地。无需账号，无需上传，没有任何遥测。',
        en: 'Conversations, memory, documents, vectors — all stored locally. No accounts, no uploads, no telemetry.',
      },
      // Quote-style accent character (left-side double quote in serif).
      accent: '"',
    },
    b: {
      eyebrow: { zh: '开放', en: 'Open' },
      title: {
        zh: '源码可读，工具可改。',
        en: 'Read the source. Change anything.',
      },
      body: {
        zh: 'MIT 开源，MCP 原生支持。模型不绑定，渠道不绑定，工具与技能都可以自己写。',
        en: 'MIT licensed, MCP-native. No model lock-in, no platform lock-in. Tools and skills are yours to write.',
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

  featureTrio: {
    // Section frames the three pillars: tools (what), channels (where),
    // memory (what it remembers). Copy is intentionally declarative and
    // spare — the section earns its weight by claiming there are *only*
    // three primitives, not by listing features.
    eyebrow: { zh: '能力构成', en: 'Built from three' },
    title: {
      zh: '一个 Agent，三件事够了。',
      en: 'Three things make an agent.',
    },
    body: {
      zh: '能动手、能被找到、记得住事。其他都是衍生。',
      en: 'It can act, it can be reached, it can remember. Everything else follows.',
    },
    cards: {
      tools: {
        kicker: { zh: '工具', en: 'Tools' },
        title: {
          zh: '不只是聊天，是真的能动手。',
          en: 'Not just chat. It does things.',
        },
        body: {
          zh: '文件、Shell、Web、MCP、知识库、记忆、定时任务、创作能力都内置在核心里，不依赖第三方插件市场。',
          en: 'Filesystem, shell, web, MCP, knowledge, memory, scheduling, creative — all built into the core. No third-party plugin marketplace required.',
        },
      },
      channels: {
        kicker: { zh: '渠道', en: 'Channels' },
        title: {
          zh: '你在哪用，它就接到哪。',
          en: 'Reach it wherever you work.',
        },
        body: {
          zh: '桌面客户端、Web 控制台、邮件，以及主流 IM —— 都是一类入口，没有谁是次等公民。',
          en: 'Desktop, web, email, every major messenger — all first-class entry points, none second-rate.',
        },
      },
      memory: {
        kicker: { zh: '记忆', en: 'Memory' },
        title: {
          zh: '记忆是文本，看得见也改得动。',
          en: 'Memory is plain text. Read it. Edit it.',
        },
        body: {
          zh: '长期事实存进 MEMORY.md，时间脉络归档进 HISTORY.md，到了上下文阈值自动整合 —— 全程明文，全程本机。',
          en: 'Durable facts in MEMORY.md, dated digest in HISTORY.md, auto-consolidated at token threshold — plaintext, on device, all the way through.',
        },
        items: [
          {
            key: 'long-term',
            name: { zh: '长期事实', en: 'Durable facts' },
            desc: {
              zh: '反复确认过的事，沉淀进 MEMORY.md。',
              en: 'What you’ve confirmed lands in MEMORY.md.',
            },
          },
          {
            key: 'history',
            name: { zh: '时间脉络', en: 'Timeline' },
            desc: {
              zh: '每段对话的摘要，按时间归档。',
              en: 'A dated digest of each conversation.',
            },
          },
          {
            key: 'auto',
            name: { zh: '自动整合', en: 'Auto-consolidate' },
            desc: {
              zh: '上下文逼近阈值时自动归档合并。',
              en: 'Auto-archives as context approaches its limit.',
            },
          },
          {
            key: 'plain',
            name: { zh: '可读可改', en: 'Plain text' },
            desc: {
              zh: 'Markdown 明文，文本编辑器即可改。',
              en: 'Plain Markdown — edit in any text editor.',
            },
          },
        ],
      },
    },
  },

  useCases: {
    eyebrow: { zh: '使用场景', en: 'Who it’s for' },
    title: { zh: '看你是谁，决定它的用法。', en: 'Who you are shapes how you use it.' },
    items: [
      {
        kicker: { zh: '给开发者', en: 'For developers' },
        title: {
          zh: '终端里随时能调的副手。',
          en: 'An assistant your terminal can summon.',
        },
        body: {
          zh: '通过 MCP 把自己的 API 接进来，调用本地仓库，跑自动化脚本，全过程都在本机。',
          en: 'Pipe in your own APIs via MCP, work on your local repo, run scripts — all without leaving the machine.',
        },
      },
      {
        kicker: { zh: '给团队', en: 'For teams' },
        title: {
          zh: '一个 Agent，整个团队都能用。',
          en: 'One agent the whole team can talk to.',
        },
        body: {
          zh: '接入飞书 / 钉钉 / 企业微信，共享知识库与团队记忆，每一次工具调用都有审计与审批。',
          en: 'Plug into Feishu / DingTalk / WeCom. Share knowledge and memory; every tool call is logged and approvable.',
        },
      },
      {
        kicker: { zh: '给研究者', en: 'For researchers' },
        title: {
          zh: '长上下文、长任务、可溯源。',
          en: 'Long context, long tasks, traceable sources.',
        },
        body: {
          zh: '阅读 PDF、整理资料、批量分析，每条引用都能回到原文的具体位置。',
          en: 'Read PDFs, organise sources, run batch analysis. Every citation points to the exact page it came from.',
        },
      },
    ],
  },

  providerStrip: {
    eyebrow: {
      zh: '主流模型与本地推理，都能跑',
      en: 'Runs with every major model — and your local one too',
    },
  },

  install: {
    // Final download CTA. Black section with a white particle field;
    // hovering left or right of center sweeps the particles into a
    // pair of { } braces around the matching button (Windows on the
    // left, macOS on the right). Copy is intentionally spare.
    eyebrow: { zh: '下载', en: 'Download' },
    title: {
      zh: '把 TokenMind 装进自己的电脑。',
      en: 'Bring TokenMind to your own machine.',
    },
    body: {
      zh: '完全免费，MIT 开源，本地运行不上传。',
      en: 'Completely free. MIT open source. Everything runs locally.',
    },
    windowsLabel: {
      zh: 'Windows 下载',
      en: 'Download for Windows',
    },
    macosLabel: {
      zh: 'macOS 下载',
      en: 'Download for macOS',
    },
    windowsHint: {
      zh: 'Windows 10 / 11 · x64',
      en: 'Windows 10 / 11 · x64',
    },
    macosHint: {
      zh: 'macOS 12+ · Apple Silicon / Intel',
      en: 'macOS 12+ · Apple Silicon / Intel',
    },
  },

  footer: {
    // Brand-led footer: tagline (left), two flat link columns (right),
    // then a giant wordmark across the page, then a thin meta strip at
    // the very bottom. All labels are i18n'd; only the HUGE "TokenMind"
    // wordmark in the middle stays English (it's the brand mark, not
    // copy). Each link entry is { key, label } where the key is used
    // by Footer.astro to resolve the URL.
    tagline: {
      zh: 'AI Agent，跑在自己的电脑上。',
      en: 'Run AI on your own machine.',
    },
    primaryLinks: [
      { key: 'download', label: { zh: '下载', en: 'Download' } },
      { key: 'docs', label: { zh: '文档', en: 'Docs' } },
      { key: 'github', label: { zh: 'GitHub', en: 'GitHub' } },
      { key: 'gitee', label: { zh: 'Gitee', en: 'Gitee' } },
    ],
    secondaryLinks: [
      { key: 'license', label: { zh: '开源协议', en: 'License' } },
      { key: 'changelog', label: { zh: '更新日志', en: 'Changelog' } },
      { key: 'contact', label: { zh: '联系我们', en: 'Contact' } },
    ],
    metaLinks: [
      { key: 'mitLicense', label: { zh: 'MIT 协议', en: 'MIT License' } },
      { key: 'privacy', label: { zh: '隐私', en: 'Privacy' } },
      { key: 'contact', label: { zh: '联系', en: 'Contact' } },
    ],
    // ICP filing displayed at the very bottom of the footer per Chinese
    // regulation. Must be a clickable link to the MIIT beian system.
    // English-route shows the same number — there's only one filing,
    // and it's a regulatory string, not translated copy.
    icp: '黑ICP备2026005421号',
  },
} as const;
