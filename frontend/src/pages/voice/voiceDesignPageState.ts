export const DESIGN_PROMPT_MIN = 5;
export const DESIGN_PROMPT_MAX = 500;
export const DESIGN_PREVIEW_MAX = 500;

export interface VoiceDesignFormInput {
  prompt: string;
  previewText: string;
  displayName: string;
}

export interface VoiceDesignValidationError {
  code: 'prompt_too_short' | 'prompt_too_long' | 'preview_too_long' | 'preview_empty';
  message: string;
}

export function validateVoiceDesignForm(
  input: VoiceDesignFormInput,
): VoiceDesignValidationError[] {
  const errors: VoiceDesignValidationError[] = [];
  const prompt = input.prompt.trim();
  if (prompt.length < DESIGN_PROMPT_MIN) {
    errors.push({
      code: 'prompt_too_short',
      message: `描述至少 ${DESIGN_PROMPT_MIN} 个字符，越具体越准确`,
    });
  } else if (prompt.length > DESIGN_PROMPT_MAX) {
    errors.push({
      code: 'prompt_too_long',
      message: `描述不能超过 ${DESIGN_PROMPT_MAX} 个字符`,
    });
  }
  const preview = input.previewText.trim();
  if (!preview) {
    errors.push({ code: 'preview_empty', message: '试听文本不能为空' });
  } else if (preview.length > DESIGN_PREVIEW_MAX) {
    errors.push({
      code: 'preview_too_long',
      message: `试听文本不能超过 ${DESIGN_PREVIEW_MAX} 个字符`,
    });
  }
  return errors;
}

export interface DesignPromptTemplate {
  id: string;
  label: string;
  prompt: string;
  preview: string;
}

export const DESIGN_PROMPT_TEMPLATES: DesignPromptTemplate[] = [
  {
    id: 'suspense_narrator',
    label: '悬疑主播',
    prompt: '悬疑故事风格的新闻主播，声音低沉磁性，节奏变化多，营造紧张感。',
    preview: '当夜幕降临，整座城市陷入沉睡，只剩一个人还站在屋顶上。',
  },
  {
    id: 'bright_vlogger',
    label: '阳光 Vlog',
    prompt: '阳光开朗的年轻女声，语气轻快有活力，适合日常 Vlog 分享。',
    preview: '哈喽大家好，今天我来到了一个超级特别的地方，走，咱们一起感受一下。',
  },
  {
    id: 'wise_teacher',
    label: '温润讲师',
    prompt: '温润儒雅的中年男声，吐字清晰，节奏平稳，适合知识讲解。',
    preview: '同学们，今天我们要学习的是一个非常重要的概念，请大家认真听。',
  },
  {
    id: 'gentle_radio',
    label: '深夜电台',
    prompt: '深夜电台的成熟女声，气音柔和，语速缓慢，带点治愈感。',
    preview: '欢迎收听今晚的节目，这是为你准备的一段安静时光。',
  },
  {
    id: 'cheerful_kid',
    label: '可爱童声',
    prompt: '活泼可爱的小孩音色，语调上扬，充满好奇心。',
    preview: '哇，这个东西好神奇呀，我从来没见过这样的！',
  },
];
