import type { CreativeCapabilitySettings } from '../types/config';

export interface MusicGenerationFormState {
  prompt: string;
  lyrics: string;
  selectedTags: string[];
  lyricsOptimizer: boolean;
  instrumental: boolean;
}

export interface MusicGenerationRequest {
  prompt: string;
  lyrics: string | null;
  lyrics_optimizer: boolean;
  is_instrumental: boolean;
}

export function buildMusicGenerationRequest(state: MusicGenerationFormState): MusicGenerationRequest {
  const prompt = state.prompt.trim();
  const tags = state.selectedTags.map((tag) => tag.trim()).filter(Boolean);
  return {
    prompt: tags.length > 0 ? `${prompt}\n\nStyle and scene tags: ${tags.join(', ')}` : prompt,
    lyrics: state.instrumental ? null : state.lyrics.trim() || null,
    lyrics_optimizer: state.instrumental ? false : state.lyricsOptimizer,
    is_instrumental: state.instrumental,
  };
}

export function isMusicCapabilityEnabled(
  capability: CreativeCapabilitySettings | null | undefined
): boolean {
  return Boolean(
    capability?.enabled &&
      capability.provider.trim() &&
      capability.model.trim()
  );
}

export function canSubmitMusicGeneration({
  capability,
  prompt,
  lyrics,
  lyricsOptimizer,
  instrumental,
  hasReferenceAudio,
  isGenerating,
}: {
  capability: CreativeCapabilitySettings | null | undefined;
  prompt: string;
  lyrics: string;
  lyricsOptimizer: boolean;
  instrumental: boolean;
  hasReferenceAudio?: boolean;
  isGenerating: boolean;
}): boolean {
  if (isGenerating || !isMusicCapabilityEnabled(capability) || !prompt.trim()) {
    return false;
  }
  return Boolean(hasReferenceAudio) || instrumental || lyricsOptimizer || Boolean(lyrics.trim());
}

export function getMusicCapabilityNotice(
  capability: CreativeCapabilitySettings | null | undefined
): string {
  if (isMusicCapabilityEnabled(capability)) {
    return '音乐模型已经启用，可以开始生成原创歌曲或纯音乐。';
  }
  if (capability?.provider.trim() && capability.model.trim()) {
    return '音乐模型已经配置完成，但当前还没有启用。';
  }
  return '还没有配置音乐模型，请先到设置中心的创作能力里配置并启用。';
}
